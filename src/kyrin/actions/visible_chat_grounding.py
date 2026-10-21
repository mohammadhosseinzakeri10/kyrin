"""Suggest only OCR-observed Telegram chat titles for misheard names.

Suggestions are not click grants. The caller asks for a numbered answer and
re-reads the same rows before using their coordinates.
"""

import re
from dataclasses import dataclass
from difflib import SequenceMatcher

from kyrin.actions.telegram_verification import (
    ChatSearchChoices,
    ChatSearchMatch,
    assess_visible_chat_choices,
)
from kyrin.text_normalization import fold_case
from kyrin.vision.text_reader import IdentifiedWindowText

_PERSIAN_LATIN = {
    "ا": "a",
    "آ": "a",
    "أ": "a",
    "إ": "a",
    "ع": "a",
    "ء": "",
    "ب": "b",
    "پ": "p",
    "ت": "t",
    "ث": "s",
    "ج": "j",
    "چ": "ch",
    "ح": "h",
    "خ": "kh",
    "د": "d",
    "ذ": "z",
    "ر": "r",
    "ز": "z",
    "ژ": "zh",
    "س": "s",
    "ش": "sh",
    "ص": "s",
    "ض": "z",
    "ط": "t",
    "ظ": "z",
    "غ": "gh",
    "ف": "f",
    "ق": "q",
    "ک": "k",
    "ك": "k",
    "گ": "g",
    "ل": "l",
    "م": "m",
    "ن": "n",
    "و": "v",
    "ه": "h",
    "ی": "y",
    "ي": "y",
    "ئ": "y",
    "ة": "h",
}


@dataclass(frozen=True, slots=True)
class VisibleGroundingAssessment:
    choices: ChatSearchChoices | None
    status: str


def _latin(value: str) -> str:
    value = fold_case(value)
    return "".join(_PERSIAN_LATIN.get(char, char) for char in value)


def _compact(value: str) -> str:
    return "".join(char for char in _latin(value) if "a" <= char <= "z")


def _consonants(value: str) -> str:
    value = _compact(value).replace("ph", "f").replace("ck", "k")
    return "".join(char for char in value if char not in "aeiouy")


def _score(spoken: str, visible: str) -> float:
    mixed_or_persian = any("\u0600" <= char <= "\u06ff" for char in visible)
    if mixed_or_persian:
        latin_prefix = re.match(r"[A-Za-z][A-Za-z0-9._-]*", visible.strip())
        if latin_prefix is not None:
            prefix_score = _score(spoken, latin_prefix.group())
            if prefix_score >= 0.86:
                return prefix_score
    heard = _compact(spoken)
    label = _compact(visible)
    if len(heard) < 4 or len(label) < 4 or heard[0] != label[0]:
        return 0.0
    # A Latin part may be enough to identify a mixed-script title.
    if len(heard) >= 5 and label.startswith(heard):
        return 1.0
    literal = SequenceMatcher(None, heard, label).ratio()
    if literal >= 0.86 and abs(len(heard) - len(label)) <= 2:
        return literal
    phonetic = SequenceMatcher(None, _consonants(spoken), _consonants(visible)).ratio()
    close_pronunciation = literal >= 0.70 and phonetic >= 0.86
    cross_script_pronunciation = (
        mixed_or_persian and literal >= 0.68 and phonetic >= 0.92
    )
    if len(_consonants(spoken)) >= 4 and (
        close_pronunciation or cross_script_pronunciation
    ):
        return 0.80 + 0.1 * phonetic
    return 0.0


def _title_phrases(observation: IdentifiedWindowText) -> tuple[str, ...]:
    if observation.image_size is None:
        return ()
    width, height = observation.image_size
    spans = observation.result.spans
    phrases: set[str] = set()
    for start, first in enumerate(spans):
        if not (
            width * 0.025 <= first.box.left < width * 0.15
            and height * 0.085 < first.box.top < height * 0.98
        ):
            continue
        parts: list[str] = []
        for span in spans[start : start + 4]:
            if (
                span.confidence is None
                or span.confidence < 0.72
                or span.box.left >= width * 0.15
                or abs(span.box.top - first.box.top) > 12
            ):
                break
            part = span.text.strip()
            if not any(char.isalpha() for char in part):
                break
            parts.append(part)
            phrase = " ".join(parts)
            if 4 <= len(phrase) <= 64:
                phrases.add(phrase)
    return tuple(phrases)


def suggest_visible_chat_choices(
    observation: IdentifiedWindowText,
    expected_app_id: str,
    expected_pid: int,
    spoken_target: str,
) -> ChatSearchChoices | None:
    """Return at most five validated, numbered suggestions in screen order."""
    return assess_visible_chat_grounding(
        observation, expected_app_id, expected_pid, spoken_target
    ).choices


def assess_visible_chat_grounding(
    observation: IdentifiedWindowText,
    expected_app_id: str,
    expected_pid: int,
    spoken_target: str,
) -> VisibleGroundingAssessment:
    """Diagnose candidate OCR rows without exposing titles in action logs."""
    if (
        observation.platform_app_id != expected_app_id
        or observation.process_id != expected_pid
        or observation.image_size is None
    ):
        return VisibleGroundingAssessment(None, "window_changed")
    candidates: list[tuple[float, str, ChatSearchMatch]] = []
    phrases = _title_phrases(observation)
    similar_count = 0
    rejected_status: str | None = None
    for phrase in phrases:
        if _score(spoken_target, phrase) < 0.86:
            continue
        similar_count += 1
        assessed = assess_visible_chat_choices(
            observation, expected_app_id, expected_pid, phrase
        )
        if assessed.choices is None:
            rejected_status = assessed.status
            continue
        for row in assessed.choices.local_results:
            score = _score(spoken_target, phrase)
            same_row = next(
                (
                    index
                    for index, (_, _, existing) in enumerate(candidates)
                    if abs(existing.top - row.top) <= 6
                    and abs(existing.left - row.left) <= 50
                ),
                None,
            )
            if same_row is None:
                candidates.append((score, phrase, row))
            elif score > candidates[same_row][0]:
                candidates[same_row] = (score, phrase, row)
    if not candidates:
        status = (
            f"similar_{similar_count}_row_{rejected_status}"
            if rejected_status is not None
            else f"similar_{similar_count}_titles_{len(phrases)}"
        )
        return VisibleGroundingAssessment(None, status)
    ranked = sorted(candidates, key=lambda item: item[0], reverse=True)
    strongest = ranked[0][0]
    ranked = [item for item in ranked if item[0] >= strongest - 0.1][:5]
    ranked.sort(key=lambda item: item[2].top)
    rows = tuple(item[2] for item in ranked)
    titles = tuple(item[1] for item in ranked)
    return VisibleGroundingAssessment(
        ChatSearchChoices(
            rows[0],
            (),
            rows[1:],
            global_section_verified=True,
            source="visible",
            grounded_titles=titles,
        ),
        f"grounded_local_{len(rows)}",
    )
