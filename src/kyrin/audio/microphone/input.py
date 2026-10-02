from collections.abc import Iterator
from threading import Event, Lock
from typing import Protocol

import sounddevice as sd  # type: ignore[import-untyped]

from kyrin.audio.audio_data import AudioData
from kyrin.audio.audio_format import AudioFormat
from kyrin.audio.microphone.errors import MicrophoneError, MicrophoneOverflowError


class _AbortableStream(Protocol):
    def abort(self) -> None: ...


class MicrophoneInput:
    def __init__(
        self,
        device: int,
        audio_format: AudioFormat,
        frames_per_chunk: int,
    ) -> None:
        if frames_per_chunk <= 0:
            raise ValueError("frames_per_chunk must be positive")

        self.device = device
        self.audio_format = audio_format
        self.frames_per_chunk = frames_per_chunk
        self._stop_requested = Event()
        self._stream_lock = Lock()
        self._active_stream: _AbortableStream | None = None

    def stop_capture(self) -> None:
        """Stop this capture session and interrupt a pending microphone read."""
        if self._stop_requested.is_set():
            return
        self._stop_requested.set()
        with self._stream_lock:
            if self._active_stream is not None:
                try:
                    self._active_stream.abort()
                except sd.PortAudioError as exc:
                    raise MicrophoneError("Could not stop microphone input") from exc

    def capture(self) -> Iterator[AudioData]:
        if self._stop_requested.is_set():
            raise MicrophoneError("Stopped microphone input cannot be restarted")
        try:
            with sd.RawInputStream(
                device=self.device,
                samplerate=self.audio_format.sample_rate,
                channels=self.audio_format.channels,
                dtype=self.audio_format.sample_format.value,
            ) as stream:
                with self._stream_lock:
                    self._active_stream = stream
                try:
                    while not self._stop_requested.is_set():
                        try:
                            data, overflowed = stream.read(self.frames_per_chunk)
                        except sd.PortAudioError:
                            if self._stop_requested.is_set():
                                return
                            raise

                        if self._stop_requested.is_set():
                            return

                        if overflowed:
                            raise MicrophoneOverflowError("Microphone input overflowed")

                        audio_bytes = bytes(data)

                        audio_chunk = AudioData(
                            data=audio_bytes,
                            audio_format=self.audio_format,
                        )

                        yield audio_chunk
                finally:
                    with self._stream_lock:
                        self._active_stream = None

        except sd.PortAudioError as exc:
            if self._stop_requested.is_set():
                return
            raise MicrophoneError("Microphone input failed") from exc
