"""Find exact visible phrases without turning OCR into an action target."""

import unicodedata
from dataclasses import dataclass
from itertools import pairwise

from kyrin.text_normalization import fold_case
from kyrin.vision.ocr.contracts import OcrResult, RecognizedText, TextBox


def _word(value: str) -> str:
    normalized = fold_case(value)
    normalized = normalized.replace("ي", "ی").replace("ك", "ک").replace("‌", "")
    return normalized.strip(" \t\r\n.,:;!?()[]{}«»\"'‘’")


def _same_line(left: RecognizedText, right: RecognizedText) -> bool:
    left_box, right_box = left.box, right.box
    overlaps_vertically = max(left_box.top, right_box.top) < min(
        left_box.top + left_box.height,
        right_box.top + right_box.height,
    )
    if any(unicodedata.bidirectional(char) in {"R", "AL"} for char in left.text):
        horizontal_gap = left_box.left - (right_box.left + right_box.width)
    else:
        horizontal_gap = right_box.left - (left_box.left + left_box.width)
    # OCR boxes can slightly overlap even for adjacent words (for example a
    # button border may be included in one word's box). Keep the allowance
    # small so two distant or unrelated spans cannot become one phrase.
    overlap_limit = min(12, max(left_box.height, right_box.height))
    gap_limit = max(12, 2 * max(left_box.height, right_box.height))
    return overlaps_vertically and -overlap_limit <= horizontal_gap <= gap_limit


@dataclass(frozen=True, slots=True)
class VisiblePhrase:
    """A text observation, not permission to click the reported image box."""

    box: TextBox
    lowest_confidence: float | None


def find_exact_phrases(result: OcrResult, phrase: str) -> tuple[VisiblePhrase, ...]:
    """Return same-line, adjacent exact matches; keep duplicates visible."""
    query = tuple(_word(part) for part in phrase.split())
    if not query or any(not part for part in query):
        return ()
    matches: list[VisiblePhrase] = []
    spans = result.spans
    for start in range(len(spans) - len(query) + 1):
        group = spans[start : start + len(query)]
        if tuple(_word(span.text) for span in group) != query:
            continue
        if any(not _same_line(left, right) for left, right in pairwise(group)):
            continue
        left = min(span.box.left for span in group)
        top = min(span.box.top for span in group)
        right = max(span.box.left + span.box.width for span in group)
        bottom = max(span.box.top + span.box.height for span in group)
        scores = [span.confidence for span in group if span.confidence is not None]
        matches.append(
            VisiblePhrase(
                TextBox(left, top, right - left, bottom - top),
                min(scores) if len(scores) == len(group) else None,
            )
        )
    return tuple(matches)


def find_compact_phrases(result: OcrResult, phrase: str) -> tuple[VisiblePhrase, ...]:
    """Match a whole visible phrase when STT or OCR omitted word spaces.

    This returns observations only. Callers must still classify the row and
    verify the window before an action; no spelling differences are repaired.
    """
    query = "".join(_word(part).replace(" ", "") for part in phrase.split())
    if not query or len(query) > 64:
        return ()
    matches: list[VisiblePhrase] = []
    spans = result.spans
    for start in range(len(spans)):
        joined = ""
        group: list[RecognizedText] = []
        for span in spans[start : start + 8]:
            if group and not _same_line(group[-1], span):
                break
            part = _word(span.text).replace(" ", "")
            if not part:
                break
            joined += part
            if not query.startswith(joined):
                break
            group.append(span)
            if joined == query:
                left = min(item.box.left for item in group)
                top = min(item.box.top for item in group)
                right = max(item.box.left + item.box.width for item in group)
                bottom = max(item.box.top + item.box.height for item in group)
                scores = [item.confidence for item in group]
                matches.append(
                    VisiblePhrase(
                        TextBox(left, top, right - left, bottom - top),
                        min(score for score in scores if score is not None)
                        if all(score is not None for score in scores)
                        else None,
                    )
                )
                break
    return tuple(matches)


def find_literal_phrases(
    result: OcrResult, phrase: str, *, allow_joined_words: bool = False
) -> tuple[VisiblePhrase, ...]:
    """Return deduplicated OCR observations for a literal spoken label.

    Joined-word matching is opt-in because some surfaces need exact spacing.
    The caller still decides whether a match is a safe actionable control.
    """
    matches = list(find_exact_phrases(result, phrase))
    if allow_joined_words:
        matches.extend(find_compact_phrases(result, phrase))
    return tuple({match.box: match for match in matches}.values())
