"""Conservative result check for the first Telegram chat action."""

from kyrin.vision.text_reader import IdentifiedWindowText
from kyrin.vision.text_targets import find_exact_phrases


def saved_messages_header_visible(
    observation: IdentifiedWindowText, expected_app_id: str, expected_pid: int
) -> bool:
    """Confirm one clear title in Telegram's upper chat pane, not a sidebar name."""
    if (
        observation.platform_app_id != expected_app_id
        or observation.process_id != expected_pid
        or observation.image_size is None
    ):
        return False
    width, height = observation.image_size
    matches = find_exact_phrases(observation.result, "Saved Messages")
    if len(matches) != 1:
        return False
    match = matches[0]
    return (
        match.lowest_confidence is not None
        and match.lowest_confidence >= 0.65
        and match.box.left >= width * 0.3
        and match.box.top <= height * 0.2
    )
