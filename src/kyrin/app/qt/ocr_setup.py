"""Discover the optional, user-scoped offline OCR runtime for Ubuntu Qt."""

import os
from pathlib import Path

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
