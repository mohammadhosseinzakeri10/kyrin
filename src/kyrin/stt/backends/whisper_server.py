"""Private loopback transport for a preloaded local whisper.cpp server."""

import io
import json
import os
import socket
import subprocess
import wave
from pathlib import Path
from time import monotonic, sleep
from typing import cast
from urllib.error import URLError
from urllib.request import ProxyHandler, Request, build_opener
from uuid import uuid4

from kyrin.stt.errors import SpeechToTextError

_HTTP = build_opener(ProxyHandler({}))


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
    """Own one CPU model process and serve local 16 kHz PCM requests."""

    def __init__(
        self, executable: str | Path, model: str | Path, *, threads: int = 4
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
        try:
            self._port = _free_loopback_port()
            self._process = subprocess.Popen(
                [
                    str(executable_path),
                    "--model",
                    str(model_path),
                    "--host",
                    "127.0.0.1",
                    "--port",
                    str(self._port),
                    "--threads",
                    str(threads),
                    "--no-gpu",
                ],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except OSError as exc:
            raise SpeechToTextError("local whisper-server could not start") from exc
        try:
            self._wait_ready()
        except OSError, SpeechToTextError:
            self.close()
            raise

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

    def transcribe(self, pcm: bytes, language: str) -> str:
        if self._process.poll() is not None:
            raise SpeechToTextError("whisper-server stopped unexpectedly")
        boundary = uuid4().hex
        body = bytearray()
        for name, value in (
            ("language", language),
            ("response_format", "json"),
            ("no_timestamps", "true"),
        ):
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
        return cast(str, payload["text"]).strip()

    def close(self) -> None:
        if self._process.poll() is None:
            self._process.terminate()
            try:
                self._process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._process.kill()
                self._process.wait()
