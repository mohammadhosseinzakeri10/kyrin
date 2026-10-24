"""Document models return text only and stay in isolated offline runtimes."""

from pathlib import Path
from subprocess import CompletedProcess, TimeoutExpired
from unittest.mock import patch

import pytest

from kyrin.vision.ocr.backends import document_trust
from kyrin.vision.ocr.backends.document import (
    DocumentOcrEngine,
    DocumentOcrGpuMemoryError,
    DocumentOcrResult,
    DocumentOcrTimeoutError,
    document_model_ready,
)
from kyrin.vision.ocr.backends.tesseract import OcrInferenceError, OcrUnavailableError
from kyrin.vision.ocr.contracts import OcrDevice, OcrDevicePreference
from tests.vision.test_document_protection_fixtures import approve_fixture


def _catalog(tmp_path: Path) -> tuple[Path, Path]:
    models = tmp_path / "models"
    runtimes = tmp_path / "runtimes"
    model = models / "surya/surya-ocr-2"
    model.mkdir(parents=True)
    (model / "config.json").write_text('{"model_type":"fixture"}', encoding="utf-8")
    (model / "model.safetensors").write_bytes(b"weights")
    python = runtimes / "document-vlm5/bin/python"
    python.parent.mkdir(parents=True)
    python.write_text("#!/bin/sh\n", encoding="utf-8")
    python.chmod(0o700)
    return models, runtimes


@pytest.fixture(autouse=True)
def reviewed_fixture_and_sandbox(monkeypatch: pytest.MonkeyPatch) -> None:
    # An explicit test-only trust decision from known fixture bytes, never from
    # the installed model. Other tests exercise rejection and the real probe.
    monkeypatch.setattr(document_trust, "APPROVED_MODELS", approve_fixture())
    monkeypatch.setattr(
        "kyrin.vision.ocr.backends.document.require_sandbox", lambda _command: None
    )


def test_document_adapter_returns_only_text_and_forces_offline(tmp_path: Path) -> None:
    models, runtimes = _catalog(tmp_path)
    engine = DocumentOcrEngine("surya", models, runtimes)
    with patch(
        "kyrin.vision.ocr.backends.document.run_worker",
        return_value=CompletedProcess(
            [],
            0,
            b'KYRIN_DOCUMENT_OCR_RESULT:{"text":"Open Telegram","device":"cpu"}\n',
            b"",
        ),
    ) as run:
        assert engine.read_text(b"png", OcrDevicePreference.CPU) == DocumentOcrResult(
            "Open Telegram", OcrDevice.CPU
        )
    assert run.call_args.args[1] == b"png"
    command = run.call_args.args[0]
    assert "--unshare-all" in command
    assert "--clearenv" in command
    for name, value in (
        ("HF_HUB_OFFLINE", "1"),
        ("TRANSFORMERS_OFFLINE", "1"),
        ("CUDA_VISIBLE_DEVICES", ""),
    ):
        index = command.index(name)
        assert command[index - 1 : index + 2] == ["--setenv", name, value]
    assert command[-5] == "-I"
    assert command[-1] == "cpu"
    assert "--dev-bind" not in command


def test_explicit_gpu_unavailable_does_not_fall_back(tmp_path: Path) -> None:
    models, runtimes = _catalog(tmp_path)
    engine = DocumentOcrEngine("surya", models, runtimes)
    with patch(
        "kyrin.vision.ocr.backends.document.run_worker",
        return_value=CompletedProcess([], 20, b"", b""),
    ) as run:
        with pytest.raises(OcrUnavailableError, match="CUDA GPU"):
            engine.read_text(b"png", OcrDevicePreference.GPU)
    run.assert_not_called()


def test_auto_uses_protected_cpu_profile(tmp_path: Path) -> None:
    models, runtimes = _catalog(tmp_path)
    engine = DocumentOcrEngine("surya", models, runtimes)
    with patch(
        "kyrin.vision.ocr.backends.document.run_worker",
        return_value=CompletedProcess(
            [], 0, b'KYRIN_DOCUMENT_OCR_RESULT:{"text":"ok","device":"cpu"}', b""
        ),
    ) as run:
        assert engine.read_text(b"png").device == OcrDevice.CPU
    assert run.call_args.args[0][-1] == "cpu"


def test_document_adapter_rejects_incomplete_or_invalid_result(tmp_path: Path) -> None:
    models, runtimes = _catalog(tmp_path)
    assert document_model_ready("surya", models, runtimes)
    (models / "surya/surya-ocr-2/model.safetensors").unlink()
    assert not document_model_ready("surya", models, runtimes)
    (models / "surya/surya-ocr-2/model.safetensors").write_bytes(b"weights")
    engine = DocumentOcrEngine("surya", models, runtimes)
    with patch(
        "kyrin.vision.ocr.backends.document.run_worker",
        return_value=CompletedProcess([], 0, b"KYRIN_DOCUMENT_OCR_RESULT:[]\n", b""),
    ):
        with pytest.raises(OcrInferenceError):
            engine.read_text(b"png")


def test_document_adapter_identifies_cpu_timeout(tmp_path: Path) -> None:
    models, runtimes = _catalog(tmp_path)
    engine = DocumentOcrEngine("surya", models, runtimes)
    with patch(
        "kyrin.vision.ocr.backends.document.run_worker",
        side_effect=TimeoutExpired(["python"], 240),
    ):
        with pytest.raises(DocumentOcrTimeoutError):
            engine.read_text(b"png")


def test_gpu_memory_error_is_distinct_from_generic_inference_failure(
    tmp_path: Path,
) -> None:
    models, runtimes = _catalog(tmp_path)
    engine = DocumentOcrEngine("surya", models, runtimes)
    # Preserve the diagnostic for a runtime unexpectedly using CUDA even under
    # the CPU-only profile. Explicit GPU requests never start the worker.
    with patch(
        "kyrin.vision.ocr.backends.document.run_worker",
        return_value=CompletedProcess(
            [], 1, b"", b"torch.OutOfMemoryError: CUDA out of memory"
        ),
    ):
        with pytest.raises(DocumentOcrGpuMemoryError):
            engine.read_text(b"png", OcrDevicePreference.AUTO)
