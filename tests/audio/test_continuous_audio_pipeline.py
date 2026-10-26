"""The live pipeline composes existing audio parts without microphone hardware."""

from collections.abc import Iterator
from threading import Event
from types import TracebackType

import numpy as np
import pytest
import sounddevice as sd  # type: ignore[import-untyped]
from pytest import MonkeyPatch

from kyrin.audio.activity.speech_activity_monitor import SpeechState, SpeechTransition
from kyrin.audio.audio_data import AudioData
from kyrin.audio.audio_format import AudioFormat, AudioSampleFormat
from kyrin.audio.continuous_audio_pipeline import ContinuousAudioPipeline
from kyrin.audio.microphone.input import MicrophoneInput

FORMAT = AudioFormat(16000, 1, AudioSampleFormat.INT16)


class FakeVad:
    input_format = FORMAT
    frames_per_window = 160

    def __init__(self, decisions: list[bool]) -> None:
        self._decisions = iter(decisions)
        self.reset_count = 0

    def detect(self, window: AudioData) -> bool:
        return next(self._decisions)

    def reset(self) -> None:
        self.reset_count += 1


class FakeInput:
    def __init__(self, chunks: list[AudioData]) -> None:
        self.chunks = chunks
        self.stop_count = 0

    def capture(self) -> Iterator[AudioData]:
        yield from self.chunks

    def stop_capture(self) -> None:
        self.stop_count += 1


def test_pipeline_forwards_every_window_and_continues_after_pause() -> None:
    data = bytes(i % 256 for i in range(3 * 160 * 2 + 2))
    source = FakeInput([AudioData(data[:6], FORMAT), AudioData(data[6:], FORMAT)])
    detector = FakeVad([True, False, True])
    pipeline = ContinuousAudioPipeline(
        source, FORMAT, detector, start_confirm_ms=1, pause_confirm_ms=1
    )

    with pipeline.open() as stream:
        frames = list(stream)

    assert b"".join(frame.audio.data for frame in frames) == data
    assert [frame.detected_speech for frame in frames] == [True, False, True, None]
    assert [frame.transition for frame in frames] == [
        SpeechTransition.STARTED,
        SpeechTransition.PAUSED,
        SpeechTransition.STARTED,
        None,
    ]
    assert frames[-1].state is SpeechState.SPEAKING
    assert source.stop_count == 1
    assert detector.reset_count == 1


def test_pipeline_resamples_before_framing() -> None:
    source_format = AudioFormat(48000, 1, AudioSampleFormat.INT16)
    source = FakeInput(
        [AudioData(np.zeros(480, dtype=np.int16).tobytes(), source_format)]
    )

    class WideVad(FakeVad):
        frames_per_window = 80

    pipeline = ContinuousAudioPipeline(source, source_format, WideVad([False, False]))

    with pipeline.open() as stream:
        frames = list(stream)

    assert len(frames) == 2
    assert all(frame.audio.audio_format == FORMAT for frame in frames)
    assert all(frame.detected_speech is False for frame in frames)


def test_pipeline_delivers_audio_before_source_ends_and_stops_early() -> None:
    class WaitingInput(FakeInput):
        def __init__(self) -> None:
            super().__init__([])
            self.waiting = Event()
            self.released = Event()

        def capture(self) -> Iterator[AudioData]:
            yield AudioData(bytes(320), FORMAT)
            self.waiting.set()
            assert self.released.wait(1)

        def stop_capture(self) -> None:
            super().stop_capture()
            self.released.set()

    source = WaitingInput()
    pipeline = ContinuousAudioPipeline(
        source, FORMAT, FakeVad([False]), max_queued_chunks=1
    )

    with pipeline.open() as stream:
        first = next(stream)
        assert first.audio.data == bytes(320)
        assert source.waiting.wait(1)

    assert source.stop_count == 1


def test_pipeline_stops_a_real_microphone_adapter_without_hardware(
    monkeypatch: MonkeyPatch,
) -> None:
    class BlockingStream:
        read_count = 0
        waiting = Event()
        released = Event()
        aborted = False
        closed = False

        def __init__(self, **kwargs: object) -> None:
            pass

        def __enter__(self) -> BlockingStream:
            return self

        def __exit__(
            self,
            exc_type: type[BaseException] | None,
            exc_value: BaseException | None,
            traceback: TracebackType | None,
        ) -> None:
            BlockingStream.closed = True

        def read(self, frames: int) -> tuple[bytes, bool]:
            BlockingStream.read_count += 1
            if BlockingStream.read_count == 1:
                return bytes(frames * 2), False
            BlockingStream.waiting.set()
            assert BlockingStream.released.wait(1)
            raise sd.PortAudioError("read interrupted")

        def abort(self) -> None:
            BlockingStream.aborted = True
            BlockingStream.released.set()

    monkeypatch.setattr(
        "kyrin.audio.microphone.input.sd.RawInputStream", BlockingStream
    )
    source = MicrophoneInput(0, FORMAT, 160)
    pipeline = ContinuousAudioPipeline(source, FORMAT, FakeVad([False]))

    with pipeline.open() as stream:
        assert next(stream).detected_speech is False
        assert BlockingStream.waiting.wait(1)

    assert BlockingStream.aborted
    assert BlockingStream.closed


def test_pipeline_rejects_overlapping_sessions() -> None:
    pipeline = ContinuousAudioPipeline(FakeInput([]), FORMAT, FakeVad([]))

    with pipeline.open():
        with pytest.raises(RuntimeError, match="active session"):
            with pipeline.open():
                pass


def test_pipeline_rejects_unsupported_source_format() -> None:
    stereo = AudioFormat(16000, 2, AudioSampleFormat.INT16)

    with pytest.raises(ValueError, match="mono INT16"):
        ContinuousAudioPipeline(FakeInput([]), stereo, FakeVad([]))
