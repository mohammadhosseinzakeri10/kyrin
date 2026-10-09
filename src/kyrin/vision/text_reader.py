"""Compose image acquisition and OCR without tying either to actions."""

from dataclasses import dataclass

from kyrin.vision.ocr.contracts import OcrEngine, OcrOptions, OcrResult
from kyrin.vision.screen_capture import ActiveWindowCapture, ScreenCapture


class WindowTextReader:
    def __init__(self, capture: ScreenCapture, ocr: OcrEngine) -> None:
        self._capture = capture
        self._ocr = ocr

    def read_selected_window(self, options: OcrOptions) -> OcrResult | None:
        """Return OCR for a freshly selected window; None means no image."""
        image = self._capture.capture_window()
        if image is None:
            return None
        return self._ocr.recognize(image, options)


@dataclass(frozen=True, slots=True)
class IdentifiedWindowText:
    """OCR and observed identity from one capture, not a future click target."""

    platform_app_id: str
    process_id: int
    result: OcrResult
    image_size: tuple[int, int] | None = None


class ActiveWindowTextReader:
    def __init__(self, capture: ActiveWindowCapture, ocr: OcrEngine) -> None:
        self._capture = capture
        self._ocr = ocr

    def read_active_window(self, options: OcrOptions) -> IdentifiedWindowText | None:
        captured = self._capture.capture_active_window()
        if captured is None:
            return None
        result = self._ocr.recognize(captured.image, options)
        return IdentifiedWindowText(
            captured.platform_app_id, captured.process_id, result
        )
