"""Document models return text only and stay in isolated offline runtimes."""

from pathlib import Path
from subprocess import CompletedProcess
from unittest.mock import patch

import pytest

from kyrin.vision.ocr.backends.document import (
    DocumentOcrEngine,
    document_model_ready,
)
from kyrin.vision.ocr.backends.tesseract import OcrInferenceError


def _catalog(tmp_path: Path) -> tuple[Path, Path]:
    models = tmp_path / "models"
    runtimes = tmp_path / "runtimes"
    model = models / "surya/surya-ocr-2"
    model.mkdir(parents=True)
    (model / "config.json").write_text("{}", encoding="utf-8")
    (model / "model.safetensors").write_bytes(b"weights")
    python = runtimes / "document-vlm5/bin/python"
    python.parent.mkdir(parents=True)
    python.write_text("#!/bin/sh\n", encoding="utf-8")
    python.chmod(0o700)
    return models, runtimes


def test_document_adapter_returns_only_text_and_forces_offline(tmp_path: Path) -> None:
    models, runtimes = _catalog(tmp_path)
    engine = DocumentOcrEngine("surya", models, runtimes)
    with patch(
        "kyrin.vision.ocr.backends.document.subprocess.run",
        return_value=CompletedProcess(
            [], 0, b'KYRIN_DOCUMENT_OCR_RESULT:"Open Telegram"\n', b""
        ),
    ) as run:
        assert engine.read_text(b"png") == "Open Telegram"
    assert run.call_args.kwargs["input"] == b"png"
    assert run.call_args.kwargs["env"]["HF_HUB_OFFLINE"] == "1"
    assert run.call_args.kwargs["env"]["TRANSFORMERS_OFFLINE"] == "1"
    assert run.call_args.args[0][1] == "-I"


def test_document_adapter_rejects_incomplete_or_invalid_result(tmp_path: Path) -> None:
    models, runtimes = _catalog(tmp_path)
    assert document_model_ready("surya", models, runtimes)
    (models / "surya/surya-ocr-2/model.safetensors").unlink()
    assert not document_model_ready("surya", models, runtimes)
    (models / "surya/surya-ocr-2/model.safetensors").write_bytes(b"weights")
    engine = DocumentOcrEngine("surya", models, runtimes)
    with patch(
        "kyrin.vision.ocr.backends.document.subprocess.run",
        return_value=CompletedProcess([], 0, b"KYRIN_DOCUMENT_OCR_RESULT:[]\n", b""),
    ):
        with pytest.raises(OcrInferenceError):
            engine.read_text(b"png")
