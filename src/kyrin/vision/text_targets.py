"""Find exact visible phrases without turning OCR into an action target."""

import unicodedata
from collections.abc import Iterator
from dataclasses import dataclass
from itertools import pairwise

from kyrin.text_normalization import fold_case
from kyrin.vision.ocr.contracts import OcrResult, RecognizedText, TextBox


def _word(value: str) -> str:
    normalized = fold_case(value)
    normalized = normalized.replace("ي", "ی").replace("ك", "ک").replace("‌", "")
    return normalized.strip(" \t\r\n.,:;!?()[]{}«»\"'‘’")


def normalize_phrase(value: str) -> str:
    """Compare literal words identically across word- and line-based engines."""
    words = tuple(_word(part) for part in fold_case(value).split())
    return " ".join(words) if words and all(words) else ""


def _direction(text: str) -> str | None:
    directions = {
        "rtl" if direction in {"R", "AL"} else "ltr"
        for char in text
        if (direction := unicodedata.bidirectional(char)) in {"R", "AL", "L"}
    }
    return next(iter(directions)) if len(directions) == 1 else None


def _adjacent(group: list[RecognizedText]) -> bool:
    # Preserve the backend's logical reading order. Within a single-script
    # run, require its direction; transitions between scripts may go either
    # way. Validate physical neighbours separately, since an embedded LTR run
    # in RTL text can jump over its own later words in logical OCR order.
    for previous, current in pairwise(group):
        direction = _direction(previous.text)
        if direction is not None and direction == _direction(current.text):
            if direction == "rtl" and current.box.left > previous.box.left:
                return False
            if direction == "ltr" and current.box.left < previous.box.left:
                return False
    physical = sorted(group, key=lambda span: span.box.left)
    for left, right in pairwise(physical):
        gap = right.box.left - (left.box.left + left.box.width)
        height = max(left.box.height, right.box.height)
        # Retain the locator's existing bounded gap and overlap allowances.
        if not -min(12, height) <= gap <= max(12, 2 * height):
            return False
    return True


@dataclass(frozen=True, slots=True)
class AssembledPhrase:
    """A contiguous same-line OCR observation, retaining display spelling."""

    text: str
    normalized: str
    box: TextBox
    lowest_confidence: float | None


def assemble_phrases(
    result: OcrResult,
    *,
    max_characters: int | None = None,
    max_spans: int | None = None,
) -> Iterator[AssembledPhrase]:
    """Build logical phrases without skipping spans or inventing confidence.

    Backend reading order is authoritative; this does not repair unordered
    OCR output or infer a reading order from coordinates. A multiline span
    cannot provide an exact single-line label box.
    """
    for start in range(len(result.spans)):
        group: list[RecognizedText] = []
        words: list[str] = []
        normalized_words: list[str] = []
        end = len(result.spans) if max_spans is None else start + max_spans
        for span in result.spans[start:end]:
            text = span.text.strip()
            normalized = normalize_phrase(text)
            if not normalized or "\n" in text or "\r" in text:
                break
            group.append(span)
            words.append(" ".join(text.split()))
            normalized_words.append(normalized)
            normalized = " ".join(normalized_words)
            if max_characters is not None and len(normalized) > max_characters:
                break
            top = max(item.box.top for item in group)
            bottom = min(item.box.top + item.box.height for item in group)
            if top >= bottom:
                break
            if not _adjacent(group):
                continue
            left = min(item.box.left for item in group)
            right = max(item.box.left + item.box.width for item in group)
            top = min(item.box.top for item in group)
            bottom = max(item.box.top + item.box.height for item in group)
            scores = [item.confidence for item in group]
            yield AssembledPhrase(
                " ".join(words),
                normalized,
                TextBox(left, top, right - left, bottom - top),
                min(score for score in scores if score is not None)
                if all(score is not None for score in scores)
                else None,
            )


@dataclass(frozen=True, slots=True)
class VisiblePhrase:
    """A text observation, not permission to click the reported image box."""

    box: TextBox
    lowest_confidence: float | None


def find_exact_phrases(result: OcrResult, phrase: str) -> tuple[VisiblePhrase, ...]:
    """Return same-line, adjacent exact matches; keep duplicates visible."""
    query = normalize_phrase(phrase)
    if not query:
        return ()
    return tuple(
        VisiblePhrase(item.box, item.lowest_confidence)
        for item in assemble_phrases(result, max_characters=len(query))
        if item.normalized == query
    )


def find_compact_phrases(result: OcrResult, phrase: str) -> tuple[VisiblePhrase, ...]:
    """Match a whole literal phrase when STT or OCR omitted word spaces.

    This returns observations only. Callers must still classify the row and
    verify the window before an action; no spelling differences are repaired.
    """
    query = normalize_phrase(phrase).replace(" ", "")
    if not query or len(query) > 64:
        return ()
    return tuple(
        VisiblePhrase(item.box, item.lowest_confidence)
        for item in assemble_phrases(result, max_spans=8)
        if item.normalized.replace(" ", "") == query
    )


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
