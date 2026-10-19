"""The isolated Paddle adapter preserves text locations and rejects bad output."""

from pathlib import Path
from subprocess import CompletedProcess
from unittest.mock import patch

import pytest

from kyrin.vision.ocr.backends.paddle import PaddleOcrEngine
from kyrin.vision.ocr.backends.tesseract import OcrInferenceError, OcrUnavailableError
from kyrin.vision.ocr.contracts import OcrOptions


def _engine(tmp_path: Path) -> PaddleOcrEngine:
    model = tmp_path / "model"
    for part in ("det", "rec"):
        folder = model / part
        folder.mkdir(parents=True)
        (folder / "inference.json").write_text("{}", encoding="utf-8")
        (folder / "inference.pdiparams").write_bytes(b"weights")
    runtime = tmp_path / "runtime"
    python = runtime / "bin/python"
    python.parent.mkdir(parents=True)
    python.write_text("#!/bin/sh\n", encoding="utf-8")
    python.chmod(0o700)
    package = runtime / "lib/python3.12/site-packages/paddleocr"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("", encoding="utf-8")
    return PaddleOcrEngine("paddle_v5_persian", model, python)


def test_paddle_result_preserves_line_box(tmp_path: Path) -> None:
    engine = _engine(tmp_path)
    framed = (
        b'KYRIN_OCR_RESULT:[{"text":"My Account",'
        b'"box":[10,20,140,55],"confidence":0.9}]\n'
    )
    with patch(
        "kyrin.vision.ocr.backends.paddle.subprocess.run",
        return_value=CompletedProcess([], 0, framed, b""),
    ) as run:
        result = engine.recognize(b"png", OcrOptions("fas+eng"))
    assert result.engine_id == "paddle_v5_persian"
    assert result.spans[0].text == "My Account"
    assert (result.spans[0].box.left, result.spans[0].box.width) == (10, 130)
    assert run.call_args.kwargs["input"] == b"png"
    assert run.call_args.kwargs["env"]["HF_HUB_OFFLINE"] == "1"


def test_paddle_rejects_unpositioned_text(tmp_path: Path) -> None:
    engine = _engine(tmp_path)
    framed = (
        b'KYRIN_OCR_RESULT:[{"text":"My Account",'
        b'"box":[0,0,0,0],"confidence":0.9}]\n'
    )
    with patch(
        "kyrin.vision.ocr.backends.paddle.subprocess.run",
        return_value=CompletedProcess([], 0, framed, b""),
    ):
        with pytest.raises(OcrInferenceError):
            engine.recognize(b"png", OcrOptions("eng"))


def test_paddle_rejects_wrong_language(tmp_path: Path) -> None:
    engine = _engine(tmp_path)
    with pytest.raises(OcrUnavailableError):
        engine.recognize(b"png", OcrOptions("deu"))


def test_paddle_vl_preserves_unknown_confidence(tmp_path: Path) -> None:
    _engine(tmp_path)
    model = tmp_path / "vl"
    model.mkdir()
    for name in ("config.json", "model.safetensors", "tokenizer.json"):
        (model / name).write_bytes(b"model")
    runtime_python = tmp_path / "runtime/bin/python"
    scipy = tmp_path / "runtime/lib/python3.12/site-packages/scipy"
    scipy.mkdir()
    (scipy / "__init__.py").write_text("", encoding="utf-8")
    vl = PaddleOcrEngine("paddle_vl16", model, runtime_python)
    framed = (
        b'KYRIN_OCR_RESULT:[{"text":"Open Telegram",'
        b'"box":[10,20,140,55],"confidence":null}]\n'
    )
    with patch(
        "kyrin.vision.ocr.backends.paddle.subprocess.run",
        return_value=CompletedProcess([], 0, framed, b""),
    ) as run:
        result = vl.recognize(b"png", OcrOptions("eng"))
    assert result.spans[0].confidence is None
    assert run.call_args.args[0][2].endswith("paddle_vl_worker.py")
