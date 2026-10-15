"""Private loopback transport for a preloaded local whisper.cpp server."""

import io
import json
import math
import os
import socket
import subprocess
import tempfile
import wave
from dataclasses import dataclass
from pathlib import Path
from time import monotonic, sleep
from typing import cast
from urllib.error import URLError
from urllib.request import ProxyHandler, Request, build_opener
from uuid import uuid4

from kyrin.stt.device import ComputeDevice
from kyrin.stt.errors import DeviceUnavailableError, SpeechToTextError

_HTTP = build_opener(ProxyHandler({}))

_LANGUAGE_CODES = {
    "english": "en",
    "persian": "fa",
    "farsi": "fa",
    "german": "de",
    "spanish": "es",
    "french": "fr",
    "italian": "it",
    "chinese": "zh",
    "hindi": "hi",
    "russian": "ru",
    "arabic": "ar",
    "japanese": "ja",
    "korean": "ko",
}


@dataclass(frozen=True, slots=True)
class WhisperResult:
    text: str
    language: str | None


def _free_loopback_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def _wav(pcm: bytes) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(16_000)
        output.writeframes(pcm)
    return buffer.getvalue()


class WhisperCppServer:
    """Own a local whisper.cpp process on the requested compute device."""

    def __init__(
        self,
        executable: str | Path,
        model: str | Path,
        *,
        threads: int = 4,
        compute_device: ComputeDevice = ComputeDevice.CPU,
    ) -> None:
        executable_path = Path(executable).expanduser().resolve()
        model_path = Path(model).expanduser().resolve()
        if not executable_path.is_file() or not os.access(executable_path, os.X_OK):
            raise FileNotFoundError(
                f"whisper-server is not executable: {executable_path}"
            )
        if not model_path.is_file():
            raise FileNotFoundError(f"Whisper model does not exist: {model_path}")
        if threads <= 0:
            raise ValueError("threads must be positive")
        if not isinstance(compute_device, ComputeDevice):
            raise ValueError("compute_device must be cpu or gpu")
        self._port = _free_loopback_port()
        arguments = [
            str(executable_path),
            "--model",
            str(model_path),
            "--host",
            "127.0.0.1",
            "--port",
            str(self._port),
            "--threads",
            str(threads),
        ]
        if compute_device is ComputeDevice.CPU:
            arguments.append("--no-gpu")
        diagnostic = (
            tempfile.TemporaryFile() if compute_device is ComputeDevice.GPU else None
        )
        try:
            try:
                self._process = subprocess.Popen(
                    arguments,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=diagnostic if diagnostic is not None else subprocess.DEVNULL,
                )
            except OSError as exc:
                raise SpeechToTextError("local whisper-server could not start") from exc
            try:
                self._wait_ready()
                if diagnostic is not None:
                    diagnostic.seek(0)
                    # A CPU-only binary can accept the same CLI flags. Require
                    # the pinned whisper.cpp runtime to confirm CUDA selection.
                    if b"whisper_backend_init_gpu: using CUDA" not in diagnostic.read():
                        raise DeviceUnavailableError(
                            "Whisper did not initialize a CUDA backend"
                        )
            except OSError, SpeechToTextError:
                self.close()
                raise
        finally:
            if diagnostic is not None:
                diagnostic.close()

    def _wait_ready(self) -> None:
        deadline = monotonic() + 30
        while monotonic() < deadline:
            if self._process.poll() is not None:
                raise SpeechToTextError(
                    "whisper-server exited during startup with status "
                    f"{self._process.returncode}"
                )
            try:
                with _HTTP.open(f"http://127.0.0.1:{self._port}/", timeout=0.5):
                    return
            except OSError, URLError:
                sleep(0.1)
        raise SpeechToTextError("whisper-server did not start within 30 seconds")

    def _request_inference(
        self,
        pcm: bytes,
        language: str,
        response_format: str,
        hints: tuple[str, ...] = (),
    ) -> dict[str, object]:
        if self._process.poll() is not None:
            raise SpeechToTextError("whisper-server stopped unexpectedly")
        boundary = uuid4().hex
        body = bytearray()
        fields = [
            ("language", language),
            ("response_format", response_format),
            ("no_timestamps", "true"),
        ]
        if hints:
            separator = "، " if language == "fa" else ", "
            fields.append(("prompt", separator.join(hints) + "."))
        for name, value in fields:
            body.extend(
                (
                    f"--{boundary}\r\n"
                    f'Content-Disposition: form-data; name="{name}"\r\n\r\n'
                    f"{value}\r\n"
                ).encode()
            )
        body.extend(
            (
                f'--{boundary}\r\nContent-Disposition: form-data; name="file"; '
                'filename="turn.wav"\r\nContent-Type: audio/wav\r\n\r\n'
            ).encode()
        )
        body.extend(_wav(pcm))
        body.extend(f"\r\n--{boundary}--\r\n".encode())
        request = Request(
            f"http://127.0.0.1:{self._port}/inference",
            data=bytes(body),
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
            method="POST",
        )
        try:
            with _HTTP.open(request, timeout=8) as response:
                payload = json.load(response)
        except (OSError, URLError, ValueError) as exc:
            raise SpeechToTextError("local Whisper inference failed") from exc
        if not isinstance(payload, dict) or not isinstance(payload.get("text"), str):
            raise SpeechToTextError("whisper-server returned an invalid response")
        return cast("dict[str, object]", payload)

    def transcribe(
        self, pcm: bytes, language: str, *, hints: tuple[str, ...] = ()
    ) -> str:
        payload = (
            self._request_inference(pcm, language, "json", hints)
            if hints
            else self._request_inference(pcm, language, "json")
        )
        return cast(str, payload["text"]).strip()

    def transcribe_auto(
        self, pcm: bytes, *, hints: tuple[str, ...] = ()
    ) -> WhisperResult:
        """Keep the original speech and report a detected language when supplied."""
        payload = (
            self._request_inference(pcm, "auto", "verbose_json", hints)
            if hints
            else self._request_inference(pcm, "auto", "verbose_json")
        )
        detected = payload.get("language")
        code = (
            _LANGUAGE_CODES.get(detected.casefold(), detected.casefold())
            if isinstance(detected, str)
            else None
        )
        if code is not None and (not 2 <= len(code) <= 3 or not code.isalpha()):
            code = None
        if code is None and isinstance(
            probabilities := payload.get("language_probabilities"), dict
        ):
            valid = {
                language: float(probability)
                for language, probability in probabilities.items()
                if isinstance(language, str)
                and 2 <= len(language) <= 3
                and language.isalpha()
                and type(probability) in (int, float)
                and math.isfinite(probability)
                and 0 <= probability <= 1
            }
            if valid:
                code = max(valid, key=lambda language: valid[language])
        return WhisperResult(cast(str, payload["text"]).strip(), code)

    def close(self) -> None:
        if self._process.poll() is None:
            try:
                self._process.terminate()
            except ProcessLookupError:
                return
            try:
                self._process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                try:
                    self._process.kill()
                except ProcessLookupError:
                    pass
                self._process.wait()
