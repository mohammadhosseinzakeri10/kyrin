"""Ground one spoken visible label in an identified window snapshot."""

from dataclasses import dataclass

from kyrin.vision.capture_geometry import CaptureGeometry
from kyrin.vision.text_reader import IdentifiedWindowText
from kyrin.vision.text_targets import assemble_phrases, find_literal_phrases


@dataclass(frozen=True, slots=True)
class VisibleControlTarget:
    left: int
    top: int
    width: int
    height: int
    image_width: int
    image_height: int
    capture_rect: tuple[int, int, int, int] | None = None
    frame_rect: tuple[int, int, int, int] | None = None
    geometry: CaptureGeometry | None = None


@dataclass(frozen=True, slots=True)
class VisibleTextOption:
    label: str
    anchor: tuple[int, int]
    geometry: CaptureGeometry | None = None


def visible_ocr_labels(
    observation: IdentifiedWindowText, app_id: str, pid: int
) -> tuple[VisibleTextOption, ...]:
    """Offer short, confident visible text as possible control names.

    Text alone does not prove that a region is clickable. The executor still
    checks the focused window and unique target before sending input.
    """
    if (observation.platform_app_id, observation.process_id) != (app_id, pid):
        return ()
    return tuple(
        VisibleTextOption(
            phrase.text,
            (
                phrase.box.left + phrase.box.width // 2,
                phrase.box.top + phrase.box.height // 2,
            ),
            observation.geometry,
        )
        for phrase in assemble_phrases(observation.result, max_characters=80)
        if phrase.lowest_confidence is not None
        and phrase.lowest_confidence >= 0.65
        and len(phrase.text) <= 80
    )


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
    return VisibleControlTarget(
        box.left,
        box.top,
        box.width,
        box.height,
        width,
        height,
        observation.capture_rect,
        observation.frame_rect,
        observation.geometry,
    )
