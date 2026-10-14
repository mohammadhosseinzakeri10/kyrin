"""Find exact visible phrases without turning OCR into an action target."""

import unicodedata
from dataclasses import dataclass
from itertools import pairwise

from kyrin.vision.ocr.contracts import OcrResult, RecognizedText, TextBox


def _word(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    normalized = normalized.replace("ي", "ی").replace("ك", "ک").replace("‌", "")
    return normalized.strip(" \t\r\n.,:;!?()[]{}«»\"'’")


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
    return overlaps_vertically and 0 <= horizontal_gap <= max(
        12, 2 * max(left_box.height, right_box.height)
    )


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
