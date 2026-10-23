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
    capture_rect: tuple[int, int, int, int] | None = None
    frame_rect: tuple[int, int, int, int] | None = None


@dataclass(frozen=True, slots=True)
class VisibleTextOption:
    label: str
    anchor: tuple[int, int]


def visible_ocr_labels(
    observation: IdentifiedWindowText, app_id: str, pid: int
) -> tuple[VisibleTextOption, ...]:
    """Offer short, confident visible text as possible control names.

    Text alone does not prove that a region is clickable. The executor still
    checks the focused window and unique target before sending input.
    """
    if (observation.platform_app_id, observation.process_id) != (app_id, pid):
        return ()
    spans = [
        span
        for span in observation.result.spans
        if span.confidence is not None
        and span.confidence >= 0.65
        and 1 <= len(span.text.strip()) <= 80
    ]
    labels: list[VisibleTextOption] = []
    for index, span in enumerate(spans):
        labels.append(
            VisibleTextOption(
                span.text.strip(),
                (
                    span.box.left + span.box.width // 2,
                    span.box.top + span.box.height // 2,
                ),
            )
        )
        # Tesseract emits words while other engines often emit whole lines.
        # Include nearby words so a label such as "Sound Settings" is usable.
        group = [span]
        for next_span in spans[index + 1 : index + 4]:
            previous = group[-1]
            if (
                abs(next_span.box.top - previous.box.top) > 8
                or next_span.box.left < previous.box.left
                or next_span.box.left - (previous.box.left + previous.box.width) > 20
            ):
                break
            group.append(next_span)
            label = " ".join(item.text.strip() for item in group)
            if len(label) <= 80:
                left = min(item.box.left for item in group)
                right = max(item.box.left + item.box.width for item in group)
                top = min(item.box.top for item in group)
                bottom = max(item.box.top + item.box.height for item in group)
                labels.append(
                    VisibleTextOption(label, ((left + right) // 2, (top + bottom) // 2))
                )
    return tuple(labels)


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
    )
