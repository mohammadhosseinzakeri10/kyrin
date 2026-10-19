"""Offline Tesseract OCR through its CLI, with no image file on disk."""

import csv
import io
import math
import subprocess
from pathlib import Path

from kyrin.vision.ocr.contracts import (
    OcrCapabilities,
    OcrDevice,
    OcrDevicePreference,
    OcrOptions,
    OcrResult,
    RecognizedText,
    TextBox,
)


class OcrUnavailableError(RuntimeError):
    """The selected OCR engine, language, or device is unavailable."""


class OcrInferenceError(RuntimeError):
    """The local OCR process failed or returned unusable output."""


def _parse_tsv(output: str) -> tuple[RecognizedText, ...]:
    try:
        rows = csv.DictReader(io.StringIO(output), delimiter="\t")
        required = {"level", "left", "top", "width", "height", "conf", "text"}
        if rows.fieldnames is None or not required.issubset(rows.fieldnames):
            raise ValueError("missing Tesseract TSV columns")
        spans: list[RecognizedText] = []
        for row in rows:
            value = row["text"]
            if row["level"] != "5" or value is None or not value.strip():
                continue
            confidence = float(row["conf"])
            if not math.isfinite(confidence) or confidence < 0:
                continue
            spans.append(
                RecognizedText(
                    value.strip(),
                    TextBox(
                        int(row["left"]),
                        int(row["top"]),
                        int(row["width"]),
                        int(row["height"]),
                    ),
                    min(confidence / 100, 1),
                )
            )
    except (TypeError, ValueError, OverflowError, KeyError) as exc:
        raise OcrInferenceError("Tesseract returned invalid position data") from exc
    return tuple(spans)


class TesseractOcrEngine:
    """Expose installed language files and honest CPU-only capability."""

    def __init__(
        self,
        tessdata_dir: Path,
        *,
        executable: str = "tesseract",
        timeout_s: float = 12.0,
        max_image_bytes: int = 32 * 1024 * 1024,
    ) -> None:
        if not tessdata_dir.is_absolute() or not tessdata_dir.is_dir():
            raise OcrUnavailableError("Tesseract language directory is unavailable")
        if not executable or not math.isfinite(timeout_s) or timeout_s <= 0:
            raise ValueError("OCR executable and timeout must be valid")
        if max_image_bytes <= 0:
            raise ValueError("maximum image size must be positive")
        languages = frozenset(
            path.stem
            for path in tessdata_dir.glob("*.traineddata")
            if path.is_file() and not path.is_symlink() and path.stem.isascii()
        )
        if not languages:
            raise OcrUnavailableError("No Tesseract language models are installed")
        self._tessdata_dir = tessdata_dir
        self._executable = executable
        self._timeout_s = timeout_s
        self._max_image_bytes = max_image_bytes
        self._capabilities = OcrCapabilities(frozenset({OcrDevice.CPU}), languages)

    @property
    def capabilities(self) -> OcrCapabilities:
        return self._capabilities

    def recognize(self, image: bytes, options: OcrOptions) -> OcrResult:
        if options.device is OcrDevicePreference.GPU:
            raise OcrUnavailableError("Tesseract does not support the selected GPU")
        if not set(options.language.split("+")).issubset(
            self._capabilities.supported_languages
        ):
            raise OcrUnavailableError("Tesseract language model is not installed")
        if not image or len(image) > self._max_image_bytes:
            raise ValueError("OCR image is empty or exceeds the size limit")
        try:
            result = subprocess.run(
                [
                    self._executable,
                    "stdin",
                    "stdout",
                    "--tessdata-dir",
                    str(self._tessdata_dir),
                    "-l",
                    options.language,
                    "--psm",
                    "3" if "fas" in options.language.split("+") else "11",
                    "-c",
                    "tessedit_create_tsv=1",
                ],
                input=image,
                capture_output=True,
                check=False,
                timeout=self._timeout_s,
            )
        except FileNotFoundError as exc:
            raise OcrUnavailableError("Tesseract executable is not installed") from exc
        except (PermissionError, subprocess.TimeoutExpired, OSError) as exc:
            raise OcrInferenceError("Tesseract could not process the image") from exc
        if result.returncode != 0:
            raise OcrInferenceError("Tesseract failed to recognize the image")
        try:
            spans = _parse_tsv(result.stdout.decode("utf-8"))
        except UnicodeError as exc:
            raise OcrInferenceError("Tesseract returned invalid text") from exc
        return OcrResult(spans, options.language, OcrDevice.CPU, "tesseract")
