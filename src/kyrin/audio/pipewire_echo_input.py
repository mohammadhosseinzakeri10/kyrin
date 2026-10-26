"""Capture an echo-cancelled PipeWire source without changing microphone logic."""

import subprocess
from collections.abc import Iterator
from threading import Event, Lock

from kyrin.audio.audio_data import AudioData
from kyrin.audio.audio_format import AudioFormat, AudioSampleFormat
from kyrin.audio.microphone.errors import MicrophoneError


class PipeWireEchoInput:
    """Read PCM from one virtual source owned by the Ubuntu session adapter."""

    audio_format = AudioFormat(16000, 1, AudioSampleFormat.INT16)
    _chunk_bytes = 640  # 20 ms of mono 16-bit PCM.

    def __init__(self, source_name: str, executable: str) -> None:
        self._source_name = source_name
        self._executable = executable
        self._stop = Event()
        self._lock = Lock()
        self._process: subprocess.Popen[bytes] | None = None

    def capture(self) -> Iterator[AudioData]:
        if self._stop.is_set():
            raise MicrophoneError("stopped echo-cancelled input cannot restart")
        try:
            process = subprocess.Popen(
                [
                    self._executable, "--target", self._source_name,
                    "--raw", "--rate", "16000", "--channels", "1",
                    "--format", "s16", "-",
                ],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
            )
        except OSError as exc:
            raise MicrophoneError("echo-cancelled input could not start") from exc
        with self._lock:
            self._process = process
        try:
            assert process.stdout is not None
            while not self._stop.is_set():
                data = process.stdout.read(self._chunk_bytes)
                if not data:
                    if self._stop.is_set():
                        return
                    raise MicrophoneError("echo-cancelled input stopped")
                if len(data) % self.audio_format.bytes_per_frame:
                    raise MicrophoneError("echo-cancelled input returned partial PCM")
                yield AudioData(data, self.audio_format)
        finally:
            self.stop_capture()
            if process.stdout is not None:
                process.stdout.close()
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=2)
            with self._lock:
                if self._process is process:
                    self._process = None

    def stop_capture(self) -> None:
        self._stop.set()
        with self._lock:
            process = self._process
        if process is not None and process.poll() is None:
            process.terminate()
