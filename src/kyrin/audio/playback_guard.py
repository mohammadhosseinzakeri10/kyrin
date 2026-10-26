"""Keep local playback out of the continuously captured audio stream."""

from collections.abc import Callable, Iterator
from typing import Protocol

from kyrin.audio.audio_data import AudioData
from kyrin.audio.audio_input import AudioInput


class PlaybackState(Protocol):
    @property
    def is_playing(self) -> bool: ...


class PlaybackGuardInput:
    """Pass through microphone chunks, or replace playback-time chunks with silence."""

    def __init__(
        self,
        source: AudioInput,
        playback: PlaybackState,
        *,
        on_guard: Callable[[bool], None] | None = None,
    ) -> None:
        self._source = source
        self._playback = playback
        self._on_guard = on_guard

    def capture(self) -> Iterator[AudioData]:
        for chunk in self._source.capture():
            guarded = self._playback.is_playing
            if self._on_guard is not None:
                self._on_guard(guarded)
            if guarded:
                yield AudioData(
                    bytes(len(chunk.data)),
                    chunk.audio_format,
                    chunk.capture_start_ns,
                )
            else:
                yield chunk

    def stop_capture(self) -> None:
        self._source.stop_capture()
