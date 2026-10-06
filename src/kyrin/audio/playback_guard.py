"""Keep local playback out of the continuously captured audio stream."""

from collections.abc import Iterator
from typing import Protocol

from kyrin.audio.audio_data import AudioData
from kyrin.audio.audio_input import AudioInput


class PlaybackState(Protocol):
    @property
    def is_active(self) -> bool: ...


class PlaybackGuardInput:
    """Pass through microphone chunks, or replace playback-time chunks with silence."""

    def __init__(self, source: AudioInput, playback: PlaybackState) -> None:
        self._source = source
        self._playback = playback

    def capture(self) -> Iterator[AudioData]:
        for chunk in self._source.capture():
            if self._playback.is_active:
                yield AudioData(bytes(len(chunk.data)), chunk.audio_format)
            else:
                yield chunk

    def stop_capture(self) -> None:
        self._source.stop_capture()
