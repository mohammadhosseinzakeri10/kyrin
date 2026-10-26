"""Explicit image/OCR pixel to logical desktop coordinate conversion."""

import json
from dataclasses import asdict, dataclass
from math import isfinite
from typing import Literal

Rect = tuple[int, int, int, int]
MAX_CAPTURE_AGE_S = 10.0


def _inside(rect: Rect, x: float, y: float) -> bool:
    left, top, width, height = rect
    return left <= x < left + width and top <= y < top + height


@dataclass(frozen=True, slots=True)
class CaptureGeometry:
    coordinate_space: Literal["logical_desktop"]
    monitor_id: int
    logical_rect: Rect
    image_size: tuple[int, int]
    scale_x: float
    scale_y: float
    padding: tuple[int, int, int, int]  # left, top, right, bottom in image px
    crop_origin: tuple[int, int]  # source-image px
    ocr_resize: tuple[float, float]  # OCR px per cropped source px
    window_token: str
    capture_id: str
    captured_at: float  # monotonic seconds on this host
    viewport_rect: Rect | None = None

    def __post_init__(self) -> None:
        if self.coordinate_space != "logical_desktop" or self.monitor_id < 0:
            raise ValueError("unsupported capture coordinate space or monitor")
        if (
            not self.window_token
            or not self.capture_id
            or not isfinite(self.captured_at)
        ):
            raise ValueError("capture identity or time is missing")
        if any(
            value <= 0 or not isfinite(value)
            for value in (*self.ocr_resize, self.scale_x, self.scale_y)
        ):
            raise ValueError("invalid capture scale")
        if any(value < 0 for value in (*self.padding, *self.crop_origin)):
            raise ValueError("invalid capture padding or crop")
        _, _, width, height = self.logical_rect
        image_width, image_height = self.image_size
        if width <= 0 or height <= 0 or image_width <= 0 or image_height <= 0:
            raise ValueError("invalid capture size")
        if self.viewport_rect is not None and min(self.viewport_rect[2:]) <= 0:
            raise ValueError("invalid viewport")
        expected_width = width * self.scale_x + self.padding[0] + self.padding[2]
        expected_height = height * self.scale_y + self.padding[1] + self.padding[3]
        if (
            abs(image_width - expected_width) > 1
            or abs(image_height - expected_height) > 1
        ):
            raise ValueError("capture size does not match explicit scale and padding")

    def to_json(self) -> str:
        return json.dumps(asdict(self), separators=(",", ":"))

    @classmethod
    def from_json(cls, value: str) -> CaptureGeometry:
        data = json.loads(value)
        if not isinstance(data, dict):
            raise ValueError("invalid capture geometry")
        for name in (
            "logical_rect",
            "image_size",
            "padding",
            "crop_origin",
            "ocr_resize",
        ):
            if name not in data or not isinstance(data[name], list):
                raise ValueError("invalid capture geometry")
            data[name] = tuple(data[name])
        if data.get("viewport_rect") is not None:
            if not isinstance(data["viewport_rect"], list):
                raise ValueError("invalid viewport")
            data["viewport_rect"] = tuple(data["viewport_rect"])
        return cls(**data)


def coordinate_to_desktop(
    geometry: CaptureGeometry,
    point: tuple[float, float],
    *,
    image_pixels: bool = False,
    target_box: Rect | None = None,
) -> tuple[int, int] | None:
    """Map an OCR pixel only if its source and desktop points stay in bounds."""
    ocr_x, ocr_y = point
    if not isfinite(ocr_x) or not isfinite(ocr_y) or min(point) < 0:
        return None
    source_x = (
        ocr_x
        if image_pixels
        else geometry.crop_origin[0] + ocr_x / geometry.ocr_resize[0]
    )
    source_y = (
        ocr_y
        if image_pixels
        else geometry.crop_origin[1] + ocr_y / geometry.ocr_resize[1]
    )
    image_width, image_height = geometry.image_size
    if not (0 <= source_x < image_width and 0 <= source_y < image_height):
        return None
    if target_box is not None and not _inside(target_box, source_x, source_y):
        return None
    logical_x = (
        geometry.logical_rect[0] + (source_x - geometry.padding[0]) / geometry.scale_x
    )
    logical_y = (
        geometry.logical_rect[1] + (source_y - geometry.padding[1]) / geometry.scale_y
    )
    if not _inside(geometry.logical_rect, logical_x, logical_y):
        return None
    viewport = geometry.viewport_rect or geometry.logical_rect
    if not _inside(viewport, logical_x, logical_y):
        return None
    x, y = round(logical_x), round(logical_y)
    if not _inside(viewport, x, y):
        return None
    if target_box is not None:
        mapped_x = (x - geometry.logical_rect[0]) * geometry.scale_x + geometry.padding[
            0
        ]
        mapped_y = (y - geometry.logical_rect[1]) * geometry.scale_y + geometry.padding[
            1
        ]
        if not _inside(target_box, mapped_x, mapped_y):
            return None
    return x, y


def capture_is_current(
    geometry: CaptureGeometry,
    window_token: str | None,
    now: float,
    *,
    max_age_s: float = MAX_CAPTURE_AGE_S,
) -> bool:
    age = now - geometry.captured_at
    return window_token == geometry.window_token and 0 <= age <= max_age_s


def capture_regions_valid(
    regions: tuple[Rect, ...], image_size: tuple[int, int]
) -> bool:
    """Require nonempty, unclipped half-open rectangles in original PNG pixels.

    The producer supplies the complete target/supporting boxes. Extra margin is
    zero: no inferred control border, desktop units or OCR-resize units enter
    this contract. Geometry/capture ID bind these boxes to the source image.
    """
    image_width, image_height = image_size
    return bool(regions) and all(
        len(rect) == 4
        and all(type(value) is int for value in rect)
        and rect[0] >= 0
        and rect[1] >= 0
        and rect[2] > 0
        and rect[3] > 0
        and rect[0] + rect[2] <= image_width
        and rect[1] + rect[3] <= image_height
        for rect in regions
    )
