"""Offline, read-only document OCR adapters; never return click coordinates."""

import json
import os
import subprocess
from pathlib import Path

from kyrin.vision.ocr.backends.tesseract import OcrInferenceError, OcrUnavailableError

_RESULT_PREFIX = "KYRIN_DOCUMENT_OCR_RESULT:"
_MAX_IMAGE_BYTES = 32 * 1024 * 1024
_MODELS = {
    "surya": ("surya/surya-ocr-2", "document-vlm5"),
    "glm": ("glm-ocr/bf16", "document-vlm5"),
    "dots": ("dots-mocr/model", "document-dots"),
}


def document_model_ready(
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


class DocumentOcrEngine:
    """A bounded subprocess that returns text only, with no action targeting API."""

    def __init__(
        self, backend: str, candidates_root: Path, runtimes_root: Path
    ) -> None:
        if not document_model_ready(backend, candidates_root, runtimes_root):
            raise OcrUnavailableError("Document OCR model or runtime is unavailable")
        model_folder, runtime_folder = _MODELS[backend]
        self.backend = backend
        self._model = candidates_root / model_folder
        self._python = runtimes_root / runtime_folder / "bin/python"
        self._cache = runtimes_root / runtime_folder / "cache"

    def read_text(self, image: bytes) -> str:
        if not image or len(image) > _MAX_IMAGE_BYTES:
            raise ValueError("Document OCR image is empty or exceeds the size limit")
        environment = os.environ.copy()
        environment.update(
            HF_HOME=str(self._cache / "huggingface"),
            XDG_CACHE_HOME=str(self._cache),
            HF_HUB_OFFLINE="1",
            TRANSFORMERS_OFFLINE="1",
            OMP_NUM_THREADS="4",
        )
        worker = Path(__file__).with_name("document_worker.py")
        try:
            process = subprocess.run(
                [str(self._python), "-I", str(worker), self.backend, str(self._model)],
                input=image,
                capture_output=True,
                timeout=240,
                check=False,
                env=environment,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            raise OcrInferenceError("Document OCR process did not finish") from error
        if process.returncode != 0:
            raise OcrInferenceError("Document OCR inference failed")
        try:
            payload = next(
                line.removeprefix(_RESULT_PREFIX)
                for line in reversed(process.stdout.decode("utf-8").splitlines())
                if line.startswith(_RESULT_PREFIX)
            )
            result = json.loads(payload)
            if not isinstance(result, str):
                raise ValueError("Document OCR did not return text")
        except (StopIteration, UnicodeError, ValueError, TypeError) as error:
            raise OcrInferenceError("Document OCR returned invalid text") from error
        return result[:16000]
