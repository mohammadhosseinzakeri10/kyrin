"""The vision reader keeps observed identity attached to its OCR result."""

from struct import pack
from typing import cast

import pytest

from kyrin.actions.visible_control import unique_visible_target
from kyrin.vision.capture_geometry import CaptureGeometry
from kyrin.vision.ocr.contracts import (
    OcrCapabilities,
    OcrDevice,
    OcrEngine,
    OcrOptions,
    OcrResult,
    RecognizedText,
    TextBox,
)
from kyrin.vision.screen_capture import ActiveWindowCapture, IdentifiedWindowImage
from kyrin.vision.text_reader import ActiveWindowTextReader

_PNG = b"\x89PNG\r\n\x1a\n" + b"pixels"


class FakeCapture:
    def __init__(self, image: IdentifiedWindowImage | None) -> None:
        self.image = image

    def capture_active_window(self) -> IdentifiedWindowImage | None:
        return self.image


class FakeOcr:
    def __init__(self) -> None:
        self.images: list[bytes] = []

    @property
    def capabilities(self) -> OcrCapabilities:
        return OcrCapabilities(frozenset({OcrDevice.CPU}), frozenset({"eng"}))

    def recognize(self, image: bytes, options: OcrOptions) -> OcrResult:
        self.images.append(image)
        return OcrResult((), options.language, OcrDevice.CPU, "fake")


def test_active_window_reader_keeps_identity_with_the_ocr_result() -> None:
    ocr = FakeOcr()
    capture = FakeCapture(IdentifiedWindowImage("browser.desktop", 123, _PNG))
    reader = ActiveWindowTextReader(
        cast(ActiveWindowCapture, capture), cast(OcrEngine, ocr)
    )
    result = reader.read_active_window(OcrOptions("eng"))
    assert result is not None
    assert result.platform_app_id == "browser.desktop"
    assert result.process_id == 123
    assert ocr.images == [_PNG]


@pytest.mark.parametrize("with_geometry", [False, True])
def test_active_reader_snapshot_can_ground_a_visible_target(
    with_geometry: bool,
) -> None:
    # PNG header dimensions suffice for fake OCR; no image decoder runs.
    png = b"\x89PNG\r\n\x1a\n" + pack(">I", 13) + b"IHDR" + pack(">II", 100, 80)
    geometry = (
        CaptureGeometry(
            "logical_desktop",
            0,
            (12, 48, 100, 80),
            (100, 80),
            1,
            1,
            (0, 0, 0, 0),
            (0, 0),
            (1, 1),
            "window",
            "capture",
            100,
        )
        if with_geometry
        else None
    )
    image = IdentifiedWindowImage(
        "browser.desktop", 123, png, (12, 48, 100, 80), (12, 48, 100, 80), geometry
    )

    class LabelOcr(FakeOcr):
        def recognize(self, image: bytes, options: OcrOptions) -> OcrResult:
            super().recognize(image, options)
            return OcrResult(
                (RecognizedText("Settings", TextBox(10, 20, 30, 10), 0.9),),
                options.language,
                OcrDevice.CPU,
                "fake",
            )

    ocr = LabelOcr()
    observation = ActiveWindowTextReader(FakeCapture(image), ocr).read_active_window(
        OcrOptions("eng")
    )
    assert observation is not None
    assert observation.image_size == (100, 80)
    assert observation.capture_rect == image.capture_rect
    assert observation.frame_rect == image.frame_rect
    assert observation.geometry == geometry
    target = unique_visible_target(observation, "browser.desktop", 123, "Settings")
    assert target is not None
    assert (target.left, target.top, target.width, target.height) == (10, 20, 30, 10)
    assert target.geometry == geometry
    assert target.capture_rect == image.capture_rect
    assert target.frame_rect == image.frame_rect
    assert unique_visible_target(observation, "other.desktop", 123, "Settings") is None
    assert ocr.images == [png]


@pytest.mark.parametrize("dimensions", [None, (0, 80), (100, 20001)])
def test_unknown_or_invalid_dimensions_do_not_create_a_target(
    dimensions: tuple[int, int] | None,
) -> None:
    png = (
        _PNG
        if dimensions is None
        else (
            b"\x89PNG\r\n\x1a\n" + pack(">I", 13) + b"IHDR" + pack(">II", *dimensions)
        )
    )
    image = IdentifiedWindowImage("browser.desktop", 123, png)
    observation = ActiveWindowTextReader(
        FakeCapture(image), FakeOcr()
    ).read_active_window(OcrOptions("eng"))
    assert observation is not None
    assert observation.image_size is None
    assert (
        unique_visible_target(observation, "browser.desktop", 123, "Settings") is None
    )


def test_missing_capture_does_not_run_ocr() -> None:
    ocr = FakeOcr()
    assert (
        ActiveWindowTextReader(FakeCapture(None), ocr).read_active_window(
            OcrOptions("eng")
        )
        is None
    )
    assert ocr.images == []
