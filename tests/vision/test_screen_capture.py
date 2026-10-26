"""Screen permission and OCR remain separate from command execution."""

import subprocess
from types import SimpleNamespace
from typing import cast
from unittest.mock import patch

from kyrin.vision.ocr.contracts import (
    OcrCapabilities,
    OcrDevice,
    OcrEngine,
    OcrOptions,
    OcrResult,
)
from kyrin.vision.platforms.ubuntu_portal import UbuntuPortalScreenCapture
from kyrin.vision.screen_capture import ScreenCapture
from kyrin.vision.text_reader import WindowTextReader


class FakeCapture:
    def __init__(self, image: bytes | None) -> None:
        self.image = image

    def capture_window(self) -> bytes | None:
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


def test_reader_only_recognizes_an_image() -> None:
    ocr = FakeOcr()
    reader = WindowTextReader(
        cast(ScreenCapture, FakeCapture(None)), cast(OcrEngine, ocr)
    )
    assert reader.read_selected_window(OcrOptions("eng")) is None
    assert not ocr.images
    reader = WindowTextReader(
        cast(ScreenCapture, FakeCapture(b"image")), cast(OcrEngine, ocr)
    )
    assert reader.read_selected_window(OcrOptions("eng")) is not None
    assert ocr.images == [b"image"]


def test_portal_bridge_accepts_only_bounded_png() -> None:
    portal = UbuntuPortalScreenCapture()
    png = b"\x89PNG\r\n\x1a\n" + b"sample"
    with patch(
        "kyrin.vision.platforms.ubuntu_portal.subprocess.run",
        return_value=SimpleNamespace(returncode=0, stdout=png),
    ):
        assert portal.capture_window() == png
    with patch(
        "kyrin.vision.platforms.ubuntu_portal.subprocess.run",
        return_value=SimpleNamespace(returncode=0, stdout=b"error"),
    ):
        assert portal.capture_window() is None
    with patch(
        "kyrin.vision.platforms.ubuntu_portal.subprocess.run",
        side_effect=subprocess.TimeoutExpired("helper", 45),
    ):
        assert portal.capture_window() is None
