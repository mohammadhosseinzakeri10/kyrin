"""Run local Omnilingual ASR checkpoints in a separate Python environment."""

import base64
import json
import os
import select
import subprocess
import tempfile
from pathlib import Path
from threading import Lock
from time import monotonic

from kyrin.stt.backends.whisper import WhisperSession
from kyrin.stt.backends.whisper_server import WhisperResult
from kyrin.stt.capabilities import SpeechToTextCapabilities
from kyrin.stt.device import ComputeDevice, DevicePreference, SpeechToTextOptions
from kyrin.stt.errors import DeviceUnavailableError, SpeechToTextError

MODEL_NAMES = tuple(
    f"omniASR_{family}_{size}_v2"
    for family in ("CTC", "LLM")
    for size in ("300M", "1B", "3B")
)
TOKENIZER_NAME = "omniASR_tokenizer_written_v2.model"
STARTUP_TIMEOUT_S = 300.0
INFERENCE_TIMEOUT_S = 120.0
CHECKPOINT_BYTES = {
    "omniASR_CTC_300M_v2": 1304065508,
    "omniASR_CTC_1B_v2": 3902956068,
    "omniASR_CTC_3B_v2": 12325920624,
    "omniASR_LLM_300M_v2": 6526183880,
    "omniASR_LLM_1B_v2": 9118733852,
    "omniASR_LLM_3B_v2": 17522679843,
}


def model_files(folder: Path) -> tuple[Path, Path]:
    """Check the exact folder layout downloaded from Meta's v2 model cards."""
    if folder.name not in MODEL_NAMES or not folder.is_dir():
        raise ValueError("Select one of the six Omnilingual ASR v2 model folders")
    checkpoint = folder / (folder.name.replace("_", "-") + ".pt")
    tokenizer = folder / TOKENIZER_NAME
    if not checkpoint.is_file() or not tokenizer.is_file():
        raise FileNotFoundError("Omnilingual ASR checkpoint or tokenizer is missing")
    if (
        checkpoint.stat().st_size != CHECKPOINT_BYTES[folder.name]
        or tokenizer.stat().st_size != 91481
    ):
        raise ValueError("Omnilingual ASR model files appear incomplete")
    return checkpoint, tokenizer


class _Worker:
    def __init__(self, python: Path, folder: Path, device: DevicePreference) -> None:
        if not python.is_file() or not os.access(python, os.X_OK):
            raise FileNotFoundError("Omnilingual ASR Python runtime is not installed")
        model_files(folder)
        script = Path(__file__).with_name("omnilingual_worker.py")
        cache_root = python.parents[4].resolve().parent / "cache"
        cache_root.mkdir(parents=True, exist_ok=True)
        environment = os.environ.copy()
        environment["XDG_CACHE_HOME"] = str(cache_root)
        environment["HF_HOME"] = str(cache_root / "huggingface")
        self._log = tempfile.TemporaryFile(mode="w+t", encoding="utf-8")
        try:
            self._process = subprocess.Popen(
                [str(python), "-u", str(script), str(folder), device.value],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=self._log,
                env=environment,
                text=True,
                encoding="utf-8",
                bufsize=1,
            )
        except OSError:
            self._log.close()
            raise
        self._lock = Lock()
        self._read_buffer = b""
        try:
            ready = self._receive(STARTUP_TIMEOUT_S)
            if ready.get("status") != "ready":
                raise SpeechToTextError(
                    str(ready.get("error", "worker failed to start"))
                )
            self.device = ComputeDevice(str(ready["device"]))
        except KeyError, ValueError, OSError, SpeechToTextError:
            self.close()
            raise

    def _receive(self, timeout_s: float) -> dict[str, object]:
        assert self._process.stdout is not None
        deadline = monotonic() + timeout_s
        while b"\n" not in self._read_buffer:
            remaining = deadline - monotonic()
            if remaining <= 0:
                self.cancel_pending_inference()
                raise SpeechToTextError("Omnilingual ASR worker response timed out")
            readable, _, _ = select.select([self._process.stdout], [], [], remaining)
            if not readable:
                self.cancel_pending_inference()
                raise SpeechToTextError("Omnilingual ASR worker response timed out")
            chunk = os.read(self._process.stdout.fileno(), 4096)
            if not chunk:
                self._log.seek(0)
                detail = self._log.read()[-1500:].strip()
                raise SpeechToTextError(
                    "Omnilingual ASR worker stopped" + (f": {detail}" if detail else "")
                )
            self._read_buffer += chunk
            if len(self._read_buffer) > 4 * 1024 * 1024:
                self.cancel_pending_inference()
                raise SpeechToTextError("Omnilingual ASR worker response is too large")
        line, self._read_buffer = self._read_buffer.split(b"\n", 1)
        try:
            message = json.loads(line)
        except json.JSONDecodeError as exc:
            raise SpeechToTextError("Omnilingual ASR worker sent invalid JSON") from exc
        if not isinstance(message, dict):
            raise SpeechToTextError("Omnilingual ASR worker sent invalid response")
        return message

    def transcribe(self, pcm: bytes, language: str) -> str:
        with self._lock:
            if self._process.poll() is not None or self._process.stdin is None:
                raise SpeechToTextError("Omnilingual ASR worker is not running")
            request = {
                "pcm": base64.b64encode(pcm).decode("ascii"),
                "language": language,
            }
            try:
                self._process.stdin.write(json.dumps(request) + "\n")
                self._process.stdin.flush()
            except (BrokenPipeError, OSError) as exc:
                raise SpeechToTextError("Omnilingual ASR worker stopped") from exc
            reply = self._receive(INFERENCE_TIMEOUT_S)
            if reply.get("status") != "ok":
                raise SpeechToTextError(str(reply.get("error", "transcription failed")))
            return str(reply.get("text", ""))

    def close(self) -> None:
        self.cancel_pending_inference()
        if self._process.stdin is not None:
            self._process.stdin.close()
        if self._process.stdout is not None:
            self._process.stdout.close()
        self._log.close()

    def cancel_pending_inference(self) -> None:
        """Stop the owned process and unblock a reader in another thread."""
        if self._process.poll() is None:
            try:
                self._process.terminate()
            except ProcessLookupError:
                pass
            try:
                self._process.wait(timeout=1)
            except subprocess.TimeoutExpired:
                try:
                    self._process.kill()
                except ProcessLookupError:
                    pass
                self._process.wait()


class OmnilingualEngine:
    """Adapt Meta's utterance inference to KYRIN's turn-aware STT contract."""

    def __init__(
        self,
        python: Path,
        model_folder: Path,
        *,
        language: str,
        device: DevicePreference,
    ) -> None:
        self._language = language
        self._worker = _Worker(python, model_folder, device)
        self._lock = Lock()
        self._active_sessions = 0
        self._closed = False
        self.capabilities = SpeechToTextCapabilities(
            supported_devices=frozenset({self._worker.device}),
            supported_languages=None if language == "auto" else frozenset({language}),
            supports_partial_updates=False,
            supports_language_detection=False,
        )

    def open_session(self, options: SpeechToTextOptions) -> WhisperSession:
        with self._lock:
            if self._closed:
                raise SpeechToTextError("Omnilingual ASR engine is closed")
            worker = self._worker
        if (
            options.device is DevicePreference.GPU
            and worker.device is not ComputeDevice.GPU
        ) or (
            options.device is DevicePreference.CPU
            and worker.device is not ComputeDevice.CPU
        ):
            raise DeviceUnavailableError("Omnilingual ASR is running on another device")
        if (
            options.language_hint is not None
            and options.language_hint != self._language
        ):
            raise SpeechToTextError("Omnilingual ASR language selection changed")
        with self._lock:
            if self._closed:
                raise SpeechToTextError("Omnilingual ASR engine is closed")
            self._active_sessions += 1
        return WhisperSession(
            lambda pcm, language: WhisperResult(
                worker.transcribe(pcm, language),
                None if language == "auto" else language,
            ),
            self._language,
            self._session_closed,
            compute_device=worker.device,
            engine_name="Omnilingual ASR",
            emit_partials=False,
        )

    def _session_closed(self) -> None:
        with self._lock:
            self._active_sessions -= 1

    def close(self) -> None:
        with self._lock:
            if self._active_sessions:
                raise SpeechToTextError("close Omnilingual ASR sessions first")
            if self._closed:
                return
            self._closed = True
        self._worker.close()

    def cancel_pending_inference(self) -> None:
        self._worker.cancel_pending_inference()
