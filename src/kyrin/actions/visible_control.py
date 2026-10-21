"""Ground one spoken visible label in an identified window snapshot."""

from dataclasses import dataclass

from kyrin.vision.text_reader import IdentifiedWindowText
from kyrin.vision.text_targets import find_literal_phrases


@dataclass(frozen=True, slots=True)
class VisibleControlTarget:
    left: int
    top: int
    width: int
    height: int
    image_width: int
    image_height: int


def unique_visible_target(
    observation: IdentifiedWindowText, app_id: str, pid: int, label: str
) -> VisibleControlTarget | None:
    """Require one confident literal label; never guess among duplicates."""
    if (observation.platform_app_id, observation.process_id) != (app_id, pid):
        return None
    if observation.image_size is None:
        return None
    width, height = observation.image_size
    matches = [
        item
        for item in find_literal_phrases(
            observation.result, label, allow_joined_words=True
        )
        if item.lowest_confidence is not None
        and item.lowest_confidence >= 0.65
        and item.box.left + item.box.width <= width
        and item.box.top + item.box.height <= height
    ]
    if len(matches) != 1:
        return None
    box = matches[0].box
    return VisibleControlTarget(box.left, box.top, box.width, box.height, width, height)
