"""Offline, read-only document OCR adapters; never return click coordinates."""

import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory

from kyrin.model_resources import MODEL_RESOURCES, ModelResources, Workload
from kyrin.vision.ocr.backends.document_sandbox import (
    require_sandbox,
    run_worker,
    sandbox_command,
)
from kyrin.vision.ocr.backends.document_trust import approved_model, verify_model
from kyrin.vision.ocr.backends.tesseract import OcrInferenceError, OcrUnavailableError
from kyrin.vision.ocr.contracts import OcrDevice, OcrDevicePreference

_RESULT_PREFIX = "KYRIN_DOCUMENT_OCR_RESULT:"
_MAX_IMAGE_BYTES = 32 * 1024 * 1024
_MODELS = {
    "surya": ("surya/surya-ocr-2", "document-vlm5"),
    "glm": ("glm-ocr/bf16", "document-vlm5"),
    "dots": ("dots-mocr/model", "document-dots"),
}


class DocumentOcrTimeoutError(OcrInferenceError):
    """The isolated document model exceeded its bounded read time."""


class DocumentOcrGpuMemoryError(OcrInferenceError):
    """The selected GPU lacks memory for this image and model."""


@dataclass(frozen=True, slots=True)
class DocumentOcrResult:
    text: str
    device: OcrDevice


def _document_model_installed(
    backend: str, candidates_root: Path, runtimes_root: Path
) -> bool:
    """Offer only complete local checkpoints with their isolated Python runtime."""
    if backend not in _MODELS:
        return False
    model_folder, runtime_folder = _MODELS[backend]
    model = candidates_root / model_folder
    python = runtimes_root / runtime_folder / "bin/python"
    if not python.is_file() or not os.access(python, os.X_OK):
        return False
    if not (model / "config.json").is_file():
        return False
    if backend == "dots":
        return all(
            (model / name).is_file()
            for name in (
                "model-00001-of-00002.safetensors",
                "model-00002-of-00002.safetensors",
                "model.safetensors.index.json",
                "modeling_dots_ocr.py",
            )
        )
    return (model / "model.safetensors").is_file()


def document_model_ready(
    backend: str, candidates_root: Path, runtimes_root: Path
) -> bool:
    """Only approved, intact checkpoints can be offered, never self-signed ones.

    Platform protection is checked before every execution; this discovery check
    does not claim that the sandbox can run on this host.
    """
    if not _document_model_installed(backend, candidates_root, runtimes_root):
        return False
    try:
        verify_model(candidates_root / _MODELS[backend][0], approved_model(backend))
    except OcrUnavailableError:
        return False
    return True


class DocumentOcrEngine:
    """A bounded subprocess that returns text only, with no action targeting API."""

    def __init__(
        self,
        backend: str,
        candidates_root: Path,
        runtimes_root: Path,
        *,
        resources: ModelResources = MODEL_RESOURCES,
    ) -> None:
        approval = approved_model(backend)
        if not _document_model_installed(backend, candidates_root, runtimes_root):
            raise OcrUnavailableError("Document OCR model or runtime is unavailable")
        verify_model(candidates_root / _MODELS[backend][0], approval)
        model_folder, runtime_folder = _MODELS[backend]
        self._resources = resources
        self.backend = backend
        self._model = candidates_root / model_folder
        self._python = runtimes_root / runtime_folder / "bin/python"

    def read_text(
        self, image: bytes, device: OcrDevicePreference = OcrDevicePreference.AUTO
    ) -> DocumentOcrResult:
        if not isinstance(device, OcrDevicePreference):
            raise ValueError("Document OCR device must be auto, cpu, or gpu")
        with self._resources.use(
            Workload.DOCUMENT_OCR, f"document_ocr:{self.backend}:{device.value}"
        ):
            return self._read_text(image, device)

    def _read_text(
        self, image: bytes, device: OcrDevicePreference
    ) -> DocumentOcrResult:
        if not image or len(image) > _MAX_IMAGE_BYTES:
            raise ValueError("Document OCR image is empty or exceeds the size limit")
        if not isinstance(device, OcrDevicePreference):
            raise ValueError("Document OCR device must be auto, cpu, or gpu")
        if device is OcrDevicePreference.GPU:
            raise OcrUnavailableError(
                "CUDA GPU is unavailable in the protected CPU document OCR profile"
            )
        runtime = self._python.parent.parent.resolve()
        worker = Path(__file__).with_name("document_worker.py").resolve()
        # Probe before making a potentially large copy. No untrusted Python is
        # started unless all namespace and mount restrictions actually work.
        command = sandbox_command(runtime, self._model.resolve(), worker)
        require_sandbox(command)
        scratch = runtime.parent / ".document-work"
        scratch.mkdir(mode=0o700, exist_ok=True)
        try:
            with TemporaryDirectory(prefix="read-", dir=scratch) as directory:
                snapshot = Path(directory)
                verify_model(self._model, approved_model(self.backend), snapshot)
                command = sandbox_command(runtime, snapshot, worker)
                process = run_worker(
                    [
                        *command,
                        "--",
                        "/runtime/bin/python",
                        "-I",
                        "/worker.py",
                        self.backend,
                        "/model",
                        "cpu",
                    ],
                    image,
                )
        except subprocess.TimeoutExpired as error:
            raise DocumentOcrTimeoutError(
                "Document OCR process exceeded four minutes"
            ) from error
        except OSError as error:
            raise OcrInferenceError("Document OCR process did not finish") from error
        if process.returncode == 20:
            raise OcrUnavailableError(
                "CUDA GPU is unavailable in this document OCR runtime"
            )
        if process.returncode != 0:
            if (
                device is not OcrDevicePreference.CPU
                and b"CUDA out of memory" in process.stderr
            ):
                raise DocumentOcrGpuMemoryError("Document OCR exhausted GPU memory")
            raise OcrInferenceError("Document OCR inference failed")
        try:
            payload = next(
                line.removeprefix(_RESULT_PREFIX)
                for line in reversed(process.stdout.decode("utf-8").splitlines())
                if line.startswith(_RESULT_PREFIX)
            )
            result = json.loads(payload)
            if not isinstance(result, dict) or not isinstance(result.get("text"), str):
                raise ValueError("Document OCR did not return text")
            raw_device = result.get("device")
            if not isinstance(raw_device, str):
                raise ValueError("Document OCR did not report its device")
            actual_device = OcrDevice(raw_device)
        except (StopIteration, UnicodeError, ValueError, TypeError) as error:
            raise OcrInferenceError("Document OCR returned invalid text") from error
        return DocumentOcrResult(result["text"][:16000], actual_device)
