"""Run optional TTS engines in their own installed Python environments."""

import base64
import json
import os
import queue
import subprocess
import sys
from pathlib import Path
from threading import Lock, Thread
from typing import Any

import numpy as np

from kyrin.responses.speech import SpeechSynthesisError

_TIMEOUT_SECONDS = 180
_MAX_AUDIO_BYTES = 16 * 1024 * 1024
_IN_WORKER_PROCESS = False


def mark_worker_process() -> None:
    """Keep an engine worker from spawning another engine worker."""
    global _IN_WORKER_PROCESS
    _IN_WORKER_PROCESS = True


def _runtime_environment(
    python: Path | None = None, family: str = ""
) -> dict[str, str]:
    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)
    environment.pop("PYTHONHOME", None)
    if (
        python is not None
        and family in {"kitten", "kokoro", "vits"}
        and sys.platform.startswith("linux")
    ):
        # CUDA wheels load NVIDIA libraries from their own runtime environment.
        site_packages = python.parent.parent / "lib"
        cuda_dirs = sorted(site_packages.glob("python*/site-packages/nvidia/*/lib"))
        if cuda_dirs:
            previous = environment.get("LD_LIBRARY_PATH", "")
            environment["LD_LIBRARY_PATH"] = os.pathsep.join(
                [*(str(path) for path in cuda_dirs), *([previous] if previous else [])]
            )
    return environment


def isolated_runtime_python(family: str) -> Path | None:
    """Find a separately installed, trusted engine runtime, without downloading."""
    # The worker must load the engine in its own process, not spawn another worker.
    if _IN_WORKER_PROCESS:
        return None
    if family not in {"chatterbox", "qwen3tts", "sherpa-gpu"}:
        return None
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData/Local"))
        executable = base / "KYRIN" / "runtimes" / "tts" / family / "Scripts/python.exe"
    elif sys.platform == "darwin":
        executable = (
            Path.home()
            / "Library/Application Support/KYRIN/runtimes/tts"
            / family
            / "bin/python"
        )
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share"))
        executable = base / "kyrin" / "runtimes" / "tts" / family / "bin/python"
    # A standard venv commonly symlinks bin/python to the system interpreter.
    return executable if executable.is_file() else None


def probe_isolated_runtime(python: Path, family: str, device: str) -> None:
    try:
        result = subprocess.run(
            [str(python), "-m", "kyrin.app.tts_worker", "probe", family, device],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
            env=_runtime_environment(python, family),
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ValueError(f"{family} isolated TTS runtime could not start") from exc
    if result.returncode:
        message = result.stdout.strip() or f"{family} runtime is unavailable"
        raise ValueError(message[:300])


class IsolatedTtsWorker:
    """Keep one model warm; exchange bounded JSON/audio with its own process."""

    def __init__(self, python: Path, family: str, folder: Path, provider: str) -> None:
        try:
            self._process = subprocess.Popen(
                [str(python), "-u", "-m", "kyrin.app.tts_worker", "serve", family],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                bufsize=1,
                env=_runtime_environment(python, family),
            )
        except OSError as exc:
            raise SpeechSynthesisError(
                f"{family} isolated runtime could not start"
            ) from exc
        self._responses: queue.Queue[str | None] = queue.Queue()
        self._lock = Lock()
        Thread(target=self._read_responses, daemon=True).start()
        try:
            self._request({"op": "load", "folder": str(folder), "provider": provider})
        except Exception:
            self.close()
            raise

    def _read_responses(self) -> None:
        assert self._process.stdout is not None
        try:
            for line in self._process.stdout:
                self._responses.put(line)
        finally:
            self._responses.put(None)

    def _request(self, message: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            try:
                if self._process.poll() is not None or self._process.stdin is None:
                    raise SpeechSynthesisError("Isolated TTS runtime stopped")
                self._process.stdin.write(json.dumps(message) + "\n")
                self._process.stdin.flush()
                line = self._responses.get(timeout=_TIMEOUT_SECONDS)
            except (OSError, BrokenPipeError, queue.Empty) as exc:
                self.close()
                raise SpeechSynthesisError(
                    "Isolated TTS runtime timed out or stopped"
                ) from exc
            if line is None:
                raise SpeechSynthesisError("Isolated TTS runtime stopped")
            try:
                answer = json.loads(line)
            except json.JSONDecodeError as exc:
                raise SpeechSynthesisError("Invalid isolated TTS response") from exc
            if not isinstance(answer, dict) or answer.get("ok") is not True:
                detail = (
                    answer.get("error", "unknown error")
                    if isinstance(answer, dict)
                    else "invalid response"
                )
                raise SpeechSynthesisError(f"Isolated TTS failed: {str(detail)[:300]}")
            return answer

    def generate(
        self, text: str, voice: str, speed: float, language: str
    ) -> tuple[np.ndarray, int]:
        answer = self._request(
            {
                "op": "generate",
                "text": text,
                "voice": voice,
                "speed": speed,
                "language": language,
            }
        )
        try:
            raw = base64.b64decode(answer["audio"], validate=True)
            sample_rate = int(answer["sample_rate"])
        except (KeyError, TypeError, ValueError) as exc:
            raise SpeechSynthesisError("Invalid isolated TTS audio") from exc
        if not raw or len(raw) > _MAX_AUDIO_BYTES or len(raw) % 4 or sample_rate <= 0:
            raise SpeechSynthesisError("Invalid isolated TTS audio")
        return np.frombuffer(raw, dtype="<f4").copy(), sample_rate

    def close(self) -> None:
        process = self._process
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=2)
        for stream in (process.stdin, process.stdout):
            if stream is not None:
                stream.close()

    def __del__(self) -> None:
        if hasattr(self, "_process"):
            self.close()
