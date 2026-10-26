"""Trusted line-protocol entry point installed inside each optional TTS runtime."""

import base64
import json
import sys
from contextlib import redirect_stdout
from pathlib import Path
from typing import Any

import numpy as np

from kyrin.tts.isolation import mark_worker_process
from kyrin.tts.memory_budget import limit_cpu_qwen_worker


def _adapter(family: str) -> Any:
    if family in {"kitten", "kokoro", "vits"}:
        from kyrin.tts.families import TTS_FAMILY_BY_KEY
        from kyrin.tts.runtime import _SherpaAdapter

        return _SherpaAdapter(TTS_FAMILY_BY_KEY[family])
    if family == "chatterbox":
        from kyrin.tts.chatterbox import ChatterboxAdapter

        return ChatterboxAdapter()
    if family == "qwen3tts":
        from kyrin.tts.qwen import QwenCustomVoiceAdapter

        return QwenCustomVoiceAdapter()
    raise ValueError("Unsupported isolated TTS family")


def _sherpa_gpu_available() -> bool:
    from ctypes import CDLL
    from importlib import import_module

    sherpa = import_module("sherpa_onnx")
    module_file = sherpa.__file__
    if module_file is None:
        return False
    provider = Path(module_file).parent / "lib/libonnxruntime_providers_cuda.so"
    if "cuda" not in sherpa.__version__ or not provider.is_file():
        return False
    try:
        driver = CDLL("libcuda.so.1")
        if driver.cuInit(0) != 0:
            return False
    except (OSError, AttributeError):
        return False
    return True


def _reply(**message: Any) -> None:
    sys.stdout.write(json.dumps(message) + "\n")
    sys.stdout.flush()


def _provider(adapter: Any, requested: str) -> str:
    if requested == "cpu":
        return "cpu"
    if requested not in {"auto", "gpu"}:
        raise ValueError("Invalid TTS device")
    if adapter.key in {"kitten", "kokoro", "vits"}:
        if _sherpa_gpu_available():
            return "cuda"
        if requested == "gpu":
            raise ValueError("TTS GPU runtime is unavailable (sherpa-onnx CUDA)")
        return "cpu"
    if not adapter._gpu_available():
        if requested == "gpu":
            raise ValueError("TTS GPU runtime is unavailable")
        return "cpu"
    from importlib import import_module

    torch = import_module("torch")
    if adapter.key == "qwen3tts":
        return "cuda:0"
    return "cuda" if torch.cuda.is_available() else "mps"


def main() -> int:
    mark_worker_process()
    if len(sys.argv) < 3:
        return 2
    mode, family = sys.argv[1:3]
    try:
        adapter = _adapter(family)
        if mode == "probe":
            from importlib.util import find_spec

            module = (
                "sherpa_onnx"
                if family in {"kitten", "kokoro", "vits"}
                else ("chatterbox" if family == "chatterbox" else "qwen_tts")
            )
            if find_spec(module) is None:
                raise ValueError(f"{family} runtime package is not installed")
            if len(sys.argv) != 4:
                return 2
            _provider(adapter, sys.argv[3])
            return 0
        if mode != "serve":
            return 2
        loaded: Any = None
        for line in sys.stdin:
            try:
                request = json.loads(line)
                if request["op"] == "load":
                    folder = Path(request["folder"])
                    with redirect_stdout(sys.stderr):
                        model = adapter.inspect(folder)
                        if model is None:
                            raise ValueError("Unsupported TTS model package")
                        provider = _provider(adapter, request["provider"])
                        if family == "qwen3tts" and provider == "cpu":
                            limit_cpu_qwen_worker()
                        loaded = adapter.load(model, folder, provider)
                    _reply(ok=True)
                elif request["op"] == "generate" and loaded is not None:
                    with redirect_stdout(sys.stderr):
                        samples, rate = adapter.generate(
                            loaded,
                            request["text"],
                            request["voice"],
                            request["speed"],
                            request["language"],
                        )
                    audio = np.asarray(samples, dtype="<f4").reshape(-1)
                    if not 0 < audio.nbytes <= 16 * 1024 * 1024:
                        raise ValueError("TTS audio is empty or too large")
                    _reply(
                        ok=True,
                        audio=base64.b64encode(audio.tobytes()).decode("ascii"),
                        sample_rate=int(rate),
                    )
                else:
                    raise ValueError("Invalid TTS worker request")
            except (
                KeyError,
                TypeError,
                ValueError,
                RuntimeError,
                ImportError,
                OSError,
            ) as exc:
                _reply(ok=False, error=str(exc)[:300])
        return 0
    except (ValueError, ImportError, OSError) as exc:
        if mode == "probe":
            sys.stdout.write(str(exc)[:300] + "\n")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
