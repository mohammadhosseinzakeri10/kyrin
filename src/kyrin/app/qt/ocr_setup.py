"""Discover the optional, user-scoped offline OCR runtime for Ubuntu Qt."""

import os
from pathlib import Path

from kyrin.app.settings import OcrSelection
from kyrin.vision.ocr.backends.tesseract import TesseractOcrEngine
from kyrin.vision.ocr.contracts import OcrEngine


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
    selection: OcrSelection | None, default_root: Path
) -> OcrEngine | None:
    """Resolve only registered adapters; a folder alone cannot execute code."""
    if selection is None:
        return installed_ocr_engine(default_root)
    if selection.backend == "tesseract":
        return installed_ocr_engine(selection.model_path)
    return None
