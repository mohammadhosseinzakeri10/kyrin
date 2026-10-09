"""Deterministic OCR adapter checks without an installed OCR executable."""

from pathlib import Path
from subprocess import CompletedProcess
from unittest.mock import patch

import pytest

from kyrin.vision.ocr.backends.tesseract import (
    OcrInferenceError,
    OcrUnavailableError,
    TesseractOcrEngine,
)
from kyrin.vision.ocr.contracts import OcrDevice, OcrDevicePreference, OcrOptions


def _engine(tmp_path: Path) -> TesseractOcrEngine:
    (tmp_path / "eng.traineddata").write_bytes(b"model")
    (tmp_path / "chi_sim.traineddata").write_bytes(b"model")
    return TesseractOcrEngine(tmp_path)


def test_tesseract_reports_cpu_and_installed_languages(tmp_path: Path) -> None:
    engine = _engine(tmp_path)
    assert engine.capabilities.supported_devices == frozenset({OcrDevice.CPU})
    assert engine.capabilities.supported_languages == frozenset({"eng", "chi_sim"})
    assert OcrOptions("chi_sim").language == "chi_sim"


def test_tesseract_parses_word_positions_and_confidence(tmp_path: Path) -> None:
    engine = _engine(tmp_path)
    output = (
        "level\tleft\ttop\twidth\theight\tconf\ttext\n"
        "5\t12\t7\t45\t18\t87.5\tTelegram\n"
        "5\t30\t40\t20\t10\t-1\t \n"
    )
    with patch(
        "kyrin.vision.ocr.backends.tesseract.subprocess.run",
        return_value=CompletedProcess([], 0, output.encode(), b""),
    ) as run:
        result = engine.recognize(b"image", OcrOptions("eng"))
    assert [span.text for span in result.spans] == ["Telegram"]
    assert result.spans[0].box.left == 12
    assert result.spans[0].confidence == 0.875
    assert result.device is OcrDevice.CPU
    assert run.call_args.kwargs["input"] == b"image"
    assert "--tessdata-dir" in run.call_args.args[0]


def test_tesseract_rejects_unsupported_gpu_and_language(tmp_path: Path) -> None:
    engine = _engine(tmp_path)
    with pytest.raises(OcrUnavailableError, match="GPU"):
        engine.recognize(b"image", OcrOptions("eng", OcrDevicePreference.GPU))
    with pytest.raises(OcrUnavailableError, match="language"):
        engine.recognize(b"image", OcrOptions("fas"))


def test_tesseract_rejects_malformed_output(tmp_path: Path) -> None:
    engine = _engine(tmp_path)
    with patch(
        "kyrin.vision.ocr.backends.tesseract.subprocess.run",
        return_value=CompletedProcess([], 0, b"bad\tcolumns\n", b""),
    ):
        with pytest.raises(OcrInferenceError, match="position"):
            engine.recognize(b"image", OcrOptions("eng"))
