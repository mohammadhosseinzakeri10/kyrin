"""Bounded live capture must signal errors and stop its worker."""

from collections.abc import Iterator
from threading import Event

import pytest

from kyrin.audio.audio_capture_queue import AudioCaptureQueue
from kyrin.audio.audio_data import AudioData
from kyrin.audio.audio_errors import (
    AudioCaptureStopError,
    AudioQueueOverflowError,
)
from kyrin.audio.audio_format import AudioFormat, AudioSampleFormat
from kyrin.audio.microphone.errors import MicrophoneError

FORMAT = AudioFormat(16000, 1, AudioSampleFormat.INT16)
CHUNK = AudioData(bytes(16), FORMAT)


class FiniteInput:
    def __init__(self, chunks: list[AudioData]) -> None:
        self._chunks = chunks
        self.finished = Event()
        self.stop_count = 0

    def capture(self) -> Iterator[AudioData]:
        try:
            yield from self._chunks
        finally:
            self.finished.set()

    def stop_capture(self) -> None:
        self.stop_count += 1


def test_capture_preserves_order_and_stops_after_source_end() -> None:
    source = FiniteInput([CHUNK, AudioData(bytes(32), FORMAT)])

    with AudioCaptureQueue(source, max_chunks=2) as capture:
        assert list(capture.chunks()) == source._chunks

    assert source.finished.is_set()
    assert source.stop_count == 1


def test_full_queue_is_an_explicit_failure() -> None:
    source = FiniteInput([CHUNK, CHUNK])

    with AudioCaptureQueue(source, max_chunks=1) as capture:
        assert source.finished.wait(1)
        with pytest.raises(AudioQueueOverflowError) as raised:
            list(capture.chunks())
        assert raised.value.buffer == "capture_queue"
        assert raised.value.pending == 2
        assert raised.value.limit == 1
        assert raised.value.unit == "chunks"


def test_source_failure_reaches_consumer() -> None:
    class FailingInput(FiniteInput):
        def capture(self) -> Iterator[AudioData]:
            raise MicrophoneError("device failed")
            yield CHUNK

    with AudioCaptureQueue(FailingInput([])) as capture:
        with pytest.raises(MicrophoneError, match="device failed"):
            list(capture.chunks())


def test_stop_releases_a_waiting_source() -> None:
    class WaitingInput(FiniteInput):
        def __init__(self) -> None:
            super().__init__([])
            self.waiting = Event()
            self.released = Event()

        def capture(self) -> Iterator[AudioData]:
            self.waiting.set()
            assert self.released.wait(1)
            return
            yield CHUNK

        def stop_capture(self) -> None:
            super().stop_capture()
            self.released.set()

    source = WaitingInput()
    with AudioCaptureQueue(source) as capture:
        assert source.waiting.wait(1)
        assert capture is not None

    assert source.stop_count == 1


def test_stop_is_idempotent() -> None:
    source = FiniteInput([])

    with AudioCaptureQueue(source) as capture:
        capture.stop()

    assert source.stop_count == 1


def test_unresponsive_source_reports_stop_timeout() -> None:
    class UnresponsiveInput(FiniteInput):
        def __init__(self) -> None:
            super().__init__([])
            self.waiting = Event()
            self.released = Event()

        def capture(self) -> Iterator[AudioData]:
            self.waiting.set()
            assert self.released.wait(1)
            return
            yield CHUNK

    source = UnresponsiveInput()
    capture = AudioCaptureQueue(source, stop_timeout_s=0.01)

    try:
        with pytest.raises(AudioCaptureStopError, match="did not stop"):
            with capture:
                assert source.waiting.wait(1)
    finally:
        source.released.set()
        if capture._thread is not None:
            capture._thread.join(1)
