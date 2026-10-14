"""Conservative OCR checks for Telegram chat navigation."""

from dataclasses import dataclass

from kyrin.vision.text_reader import IdentifiedWindowText
from kyrin.vision.text_targets import find_exact_phrases


@dataclass(frozen=True, slots=True)
class ChatSearchMatch:
    """A single visible result in window-image coordinates, not a click grant."""

    left: int
    top: int
    width: int
    height: int
    image_width: int
    image_height: int


def _same_window(
    observation: IdentifiedWindowText, expected_app_id: str, expected_pid: int
) -> bool:
    return (
        observation.platform_app_id == expected_app_id
        and observation.process_id == expected_pid
        and observation.image_size is not None
    )


def unique_search_result(
    observation: IdentifiedWindowText,
    expected_app_id: str,
    expected_pid: int,
    target: str,
) -> ChatSearchMatch | None:
    """Accept one exact, clear title in the left results pane below search."""
    if not _same_window(observation, expected_app_id, expected_pid):
        return None
    assert observation.image_size is not None
    width, height = observation.image_size
    candidates = [
        match
        for match in find_exact_phrases(observation.result, target)
        if match.lowest_confidence is not None
        and match.lowest_confidence >= 0.75
        and match.box.left >= 0
        and match.box.left + match.box.width < width * 0.3
        and height * 0.12 < match.box.top < height * 0.75
    ]
    if len(candidates) != 1:
        return None
    box = candidates[0].box
    return ChatSearchMatch(box.left, box.top, box.width, box.height, width, height)


def chat_header_visible(
    observation: IdentifiedWindowText,
    expected_app_id: str,
    expected_pid: int,
    target: str,
) -> bool:
    """Confirm a unique exact title in the upper right chat pane."""
    if not _same_window(observation, expected_app_id, expected_pid):
        return False
    assert observation.image_size is not None
    width, height = observation.image_size
    matches = find_exact_phrases(observation.result, target)
    if len(matches) != 1:
        return False
    match = matches[0]
    return (
        match.lowest_confidence is not None
        and match.lowest_confidence >= 0.65
        and match.box.left >= width * 0.3
        and match.box.top <= height * 0.2
    )


def saved_messages_header_visible(
    observation: IdentifiedWindowText, expected_app_id: str, expected_pid: int
) -> bool:
    """Confirm one clear title in Telegram's upper chat pane, not a sidebar name."""
    return chat_header_visible(
        observation, expected_app_id, expected_pid, "Saved Messages"
    )
