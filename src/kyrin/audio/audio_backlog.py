"""Bound audio waiting for an independent processing worker by audio duration."""

from collections import deque
from dataclasses import dataclass
from enum import StrEnum
from threading import Condition

from kyrin.audio.audio_data import AudioData
from kyrin.audio.audio_errors import AudioQueueOverflowError
from kyrin.audio.audio_format import AudioFormat


class BacklogState(StrEnum):
    WAIT = "wait"
    READY = "ready"


@dataclass(frozen=True, slots=True)
class BacklogNotice:
    """A state change for the UI; it does not itself display a message."""

    state: BacklogState
    pending_ms: int


class AudioBacklog:
    """FIFO with bounded pending audio, including the chunk under inference."""

    def __init__(
        self,
        audio_format: AudioFormat,
        *,
        warning_ms: int = 1000,
        recovery_ms: int = 250,
        maximum_ms: int = 5000,
    ) -> None:
        if not 0 <= recovery_ms < warning_ms < maximum_ms:
            raise ValueError("require 0 <= recovery_ms < warning_ms < maximum_ms")
        self.audio_format = audio_format
        self.warning_ms = warning_ms
        self.recovery_ms = recovery_ms
        self.maximum_ms = maximum_ms
        self._chunks: deque[AudioData] = deque()
        self._condition = Condition()
        self._pending_frames = 0
        self._warned = False
        self._closed = False
        self._aborted = False

    def _duration_ms(self) -> int:
        return (self._pending_frames * 1000) // self.audio_format.sample_rate

    def put(self, chunk: AudioData) -> BacklogNotice | None:
        if chunk.audio_format != self.audio_format:
            raise ValueError("audio backlog format changed")
        if not chunk.data:
            return None
        frames = len(chunk.data) // self.audio_format.bytes_per_frame
        with self._condition:
            if self._closed or self._aborted:
                raise RuntimeError("audio backlog is closed")
            pending = self._pending_frames + frames
            if pending * 1000 > self.maximum_ms * self.audio_format.sample_rate:
                raise AudioQueueOverflowError(
                    "STT audio backlog exceeded its duration limit"
                )
            self._chunks.append(chunk)
            self._pending_frames = pending
            self._condition.notify()
            if not self._warned and pending * 1000 >= (
                self.warning_ms * self.audio_format.sample_rate
            ):
                self._warned = True
                return BacklogNotice(BacklogState.WAIT, self._duration_ms())
        return None

    def get(self) -> AudioData | None:
        with self._condition:
            while not self._chunks and not self._closed and not self._aborted:
                self._condition.wait()
            if self._aborted or not self._chunks:
                return None
            return self._chunks.popleft()

    def complete(self, chunk: AudioData) -> BacklogNotice | None:
        frames = len(chunk.data) // self.audio_format.bytes_per_frame
        with self._condition:
            self._pending_frames -= frames
            if self._warned and self._pending_frames * 1000 <= (
                self.recovery_ms * self.audio_format.sample_rate
            ):
                self._warned = False
                return BacklogNotice(BacklogState.READY, self._duration_ms())
        return None

    def close(self) -> None:
        with self._condition:
            self._closed = True
            self._condition.notify_all()

    def abort(self) -> None:
        with self._condition:
            self._aborted = True
            self._chunks.clear()
            self._condition.notify_all()
