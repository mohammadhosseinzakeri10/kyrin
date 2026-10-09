"""The vision reader keeps observed identity attached to its OCR result."""

from typing import cast

from kyrin.vision.ocr.contracts import (
    OcrCapabilities,
    OcrDevice,
    OcrEngine,
    OcrOptions,
    OcrResult,
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
