"""Run a locally installed PaddleOCR pipeline in its isolated Python runtime."""

import json
import math
import os
import subprocess
from pathlib import Path

from kyrin.vision.ocr.backends.tesseract import OcrInferenceError, OcrUnavailableError
from kyrin.vision.ocr.contracts import (
    OcrCapabilities,
    OcrDevice,
    OcrDevicePreference,
    OcrOptions,
    OcrResult,
    RecognizedText,
    TextBox,
)

_MODEL_NAMES = {
    "paddle_v5_persian": ("PP-OCRv5_mobile_det", "arabic_PP-OCRv5_mobile_rec"),
    "paddle_v6_small": ("PP-OCRv6_small_det", "PP-OCRv6_small_rec"),
    "paddle_v6_medium": ("PP-OCRv6_medium_det", "PP-OCRv6_medium_rec"),
}
_RESULT_PREFIX = "KYRIN_OCR_RESULT:"
_MAX_IMAGE_BYTES = 32 * 1024 * 1024


def paddle_model_ready(backend: str, model_path: Path, runtime_python: Path) -> bool:
    """Check the exact downloaded pair and the separate runtime before selection."""
    if backend not in (*_MODEL_NAMES, "paddle_vl16") or not runtime_python.is_file():
        return False
    if not os.access(runtime_python, os.X_OK):
        return False
    site_packages = runtime_python.parent.parent / "lib"
    if not any(site_packages.glob("python*/site-packages/paddleocr/__init__.py")):
        return False
    if backend == "paddle_vl16":
        return all(
            (model_path / name).is_file()
            for name in ("config.json", "model.safetensors", "tokenizer.json")
        ) and any(site_packages.glob("python*/site-packages/scipy/__init__.py"))
    return all(
        (model_path / part / "inference.json").is_file()
        and (model_path / part / "inference.pdiparams").is_file()
        for part in ("det", "rec")
    )


class PaddleOcrEngine:
    def __init__(self, backend: str, model_path: Path, runtime_python: Path) -> None:
        if not paddle_model_ready(backend, model_path, runtime_python):
            raise OcrUnavailableError("PaddleOCR model or runtime is unavailable")
        self._backend = backend
        self._model_path = model_path
        self._runtime_python = runtime_python
        languages = {"eng", "fas"} if backend == "paddle_v5_persian" else {"eng"}
        self._capabilities = OcrCapabilities(
            frozenset({OcrDevice.CPU}), frozenset(languages)
        )

    @property
    def capabilities(self) -> OcrCapabilities:
        return self._capabilities

    def recognize(self, image: bytes, options: OcrOptions) -> OcrResult:
        if options.device is OcrDevicePreference.GPU:
            raise OcrUnavailableError("This PaddleOCR runtime is CPU-only")
        if not set(options.language.split("+")).issubset(
            self._capabilities.supported_languages
        ):
            raise OcrUnavailableError(
                "Selected PaddleOCR model does not support this language"
            )
        if not image or len(image) > _MAX_IMAGE_BYTES:
            raise ValueError("OCR image is empty or exceeds the size limit")
        if self._backend == "paddle_vl16":
            worker = Path(__file__).with_name("paddle_vl_worker.py")
            arguments = [str(self._model_path)]
        else:
            det_name, rec_name = _MODEL_NAMES[self._backend]
            worker = Path(__file__).with_name("paddle_worker.py")
            arguments = [str(self._model_path), det_name, rec_name]
        cache = self._runtime_python.parent.parent / "cache"
        environment = os.environ.copy()
        environment.update(
            PADDLE_PDX_CACHE_HOME=str(cache / "paddlex"),
            HF_HOME=str(cache / "huggingface"),
            XDG_CACHE_HOME=str(cache),
            HF_HUB_OFFLINE="1",
            TRANSFORMERS_OFFLINE="1",
            PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK="True",
        )
        try:
            process = subprocess.run(
                [str(self._runtime_python), "-I", str(worker), *arguments],
                input=image,
                capture_output=True,
                timeout=90 if self._backend == "paddle_vl16" else 60,
                check=False,
                env=environment,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            raise OcrInferenceError("PaddleOCR process did not finish") from error
        if process.returncode != 0:
            raise OcrInferenceError("PaddleOCR inference failed")
        try:
            payload = next(
                line.removeprefix(_RESULT_PREFIX)
                for line in reversed(process.stdout.decode("utf-8").splitlines())
                if line.startswith(_RESULT_PREFIX)
            )
            data = json.loads(payload)
            spans = tuple(self._parse_span(item) for item in data)
        except (StopIteration, UnicodeError, ValueError, TypeError, KeyError) as error:
            raise OcrInferenceError(
                "PaddleOCR returned invalid position data"
            ) from error
        return OcrResult(spans, options.language, OcrDevice.CPU, self._backend)

    @staticmethod
    def _parse_span(item: object) -> RecognizedText:
        if not isinstance(item, dict):
            raise ValueError("invalid PaddleOCR span")
        text = item["text"]
        box = item["box"]
        confidence = item["confidence"]
        if not isinstance(text, str) or not isinstance(box, list) or len(box) != 4:
            raise ValueError("invalid PaddleOCR span")
        if not all(
            isinstance(value, int) and not isinstance(value, bool) for value in box
        ):
            raise ValueError("invalid PaddleOCR box")
        if confidence is not None and (
            not isinstance(confidence, (int, float)) or not math.isfinite(confidence)
        ):
            raise ValueError("invalid PaddleOCR confidence")
        left, top, right, bottom = box
        return RecognizedText(
            text,
            TextBox(left, top, right - left, bottom - top),
            max(0.0, min(float(confidence), 1.0))
            if confidence is not None
            else None,
        )
