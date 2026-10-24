"""Compose image acquisition and OCR without tying either to actions."""

from dataclasses import dataclass, replace
from struct import unpack_from

from kyrin.vision.capture_geometry import CaptureGeometry
from kyrin.vision.ocr.contracts import OcrEngine, OcrOptions, OcrResult
from kyrin.vision.screen_capture import (
    ActiveWindowCapture,
    IdentifiedWindowImage,
    ScreenCapture,
)


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
    """OCR and identity from one snapshot, not a future click target.

    Result boxes use original PNG pixels. Qt has already undone OCR crop and
    resize; geometry retains their provenance, so actuators map with
    ``image_pixels=True`` and must not apply those transforms again.
    """

    platform_app_id: str
    process_id: int
    result: OcrResult
    image_size: tuple[int, int] | None = None
    capture_rect: tuple[int, int, int, int] | None = None
    frame_rect: tuple[int, int, int, int] | None = None
    geometry: CaptureGeometry | None = None

    @classmethod
    def from_capture(
        cls,
        captured: IdentifiedWindowImage,
        result: OcrResult,
        *,
        crop_origin: tuple[int, int] | None = None,
        ocr_resize: tuple[float, float] | None = None,
    ) -> IdentifiedWindowText:
        """Attach source metadata to OCR already mapped to original PNG pixels.

        Crop/resize describe provenance only; this factory never transforms boxes.
        Missing PNG dimensions remain unknown rather than guessed from rectangles.
        """
        geometry = captured.geometry
        if geometry is not None and (crop_origin is not None or ocr_resize is not None):
            geometry = replace(
                geometry,
                crop_origin=crop_origin
                if crop_origin is not None
                else geometry.crop_origin,
                ocr_resize=ocr_resize
                if ocr_resize is not None
                else geometry.ocr_resize,
            )
        return cls(
            captured.platform_app_id,
            captured.process_id,
            result,
            _png_size(captured.image),
            captured.capture_rect,
            captured.frame_rect,
            geometry,
        )


def _png_size(image: bytes) -> tuple[int, int] | None:
    if len(image) < 24 or image[12:16] != b"IHDR":
        return None
    width, height = unpack_from(">II", image, 16)
    if not (0 < width <= 20000 and 0 < height <= 20000):
        return None
    return width, height


class ActiveWindowTextReader:
    def __init__(self, capture: ActiveWindowCapture, ocr: OcrEngine) -> None:
        self._capture = capture
        self._ocr = ocr

    def read_active_window(self, options: OcrOptions) -> IdentifiedWindowText | None:
        captured = self._capture.capture_active_window()
        if captured is None:
            return None
        result = self._ocr.recognize(captured.image, options)
        return IdentifiedWindowText.from_capture(captured, result)
