"""Discover the optional, user-scoped offline OCR runtime for Ubuntu Qt."""

import os
from pathlib import Path

from kyrin.app.settings import OcrSelection
from kyrin.vision.ocr.backends.paddle import PaddleOcrEngine, paddle_model_ready
from kyrin.vision.ocr.backends.tesseract import TesseractOcrEngine
from kyrin.vision.ocr.contracts import OcrEngine

PADDLE_CHOICES = (
    ("paddle_v5_persian", "PaddleOCR v5 · Persian + English", "v5-persian"),
    ("paddle_v6_small", "PaddleOCR v6 · Small (English)", "v6-small"),
    ("paddle_v6_medium", "PaddleOCR v6 · Medium (English)", "v6-medium"),
)
PADDLE_VL_CHOICE = ("paddle_vl16", "PaddleOCR-VL 1.6 · read only (slow CPU)", "vl-1.6")


def installed_ocr_engine(root: Path) -> OcrEngine | None:
    """Return an OCR adapter without downloading or installing anything."""
    executable = root / "tesseract-local"
    tessdata = root / "runtime/usr/share/tesseract-ocr/5/tessdata"
    if (
        not executable.is_file()
        or not os.access(executable, os.X_OK)
        or not (tessdata / "eng.traineddata").is_file()
    ):
        return None
    return TesseractOcrEngine(tessdata, executable=str(executable))


def selected_ocr_engine(
    selection: OcrSelection | None,
    default_root: Path,
    *,
    candidates_root: Path | None = None,
    paddle_python: Path | None = None,
    paddle_vl_python: Path | None = None,
) -> OcrEngine | None:
    """Resolve only registered adapters; a folder alone cannot execute code."""
    if selection is None:
        return installed_ocr_engine(default_root)
    if selection.backend == "tesseract":
        installed = installed_ocr_engine(selection.model_path)
        if installed is not None:
            return installed
        executable = default_root / "tesseract-local"
        if (
            executable.is_file()
            and os.access(executable, os.X_OK)
            and (selection.model_path / "eng.traineddata").is_file()
        ):
            return TesseractOcrEngine(
                selection.model_path, executable=str(executable)
            )
    if candidates_root is not None and paddle_python is not None:
        for backend, _, folder in PADDLE_CHOICES:
            expected = candidates_root / "paddleocr" / folder
            if (
                selection.backend == backend
                and selection.model_path == expected
                and paddle_model_ready(backend, expected, paddle_python)
            ):
                return PaddleOcrEngine(backend, expected, paddle_python)
    if candidates_root is not None and paddle_vl_python is not None:
        backend, _, folder = PADDLE_VL_CHOICE
        expected = candidates_root / "paddleocr" / folder
        if (
            selection.backend == backend
            and selection.model_path == expected
            and paddle_model_ready(backend, expected, paddle_vl_python)
        ):
            return PaddleOcrEngine(backend, expected, paddle_vl_python)
    return None
