"""Live capture shares every source chunk with activity and transcription."""

from collections.abc import Iterator, Sequence
from threading import Event

import pytest

from kyrin.audio.activity.speech_activity_monitor import SpeechActivityFrame
from kyrin.audio.audio_backlog import AudioBacklog, BacklogNotice, BacklogState
from kyrin.audio.audio_data import AudioData
from kyrin.audio.audio_errors import AudioCaptureStopError, AudioQueueOverflowError
from kyrin.audio.audio_format import AudioFormat, AudioSampleFormat
from kyrin.audio.live_speech_pipeline import LiveSpeechPipeline
from kyrin.stt.capabilities import SpeechToTextCapabilities
from kyrin.stt.device import ComputeDevice, SpeechToTextOptions
from kyrin.stt.transcript import TranscriptStatus, TranscriptUpdate

FORMAT = AudioFormat(16000, 1, AudioSampleFormat.INT16)


class Source:
    def __init__(self, chunks: list[AudioData]) -> None:
        self.chunks = chunks
        self.capture_count = 0
        self.stop_count = 0

    def capture(self) -> Iterator[AudioData]:
        self.capture_count += 1
        yield from self.chunks

    def stop_capture(self) -> None:
        self.stop_count += 1


class Detector:
    input_format = FORMAT
    frames_per_window = 160

    def __init__(self, decisions: list[bool]) -> None:
        self.decisions = iter(decisions)
        self.seen: list[bytes] = []

    def detect(self, window: AudioData) -> bool:
        self.seen.append(window.data)
        return next(self.decisions)

    def reset(self) -> None:
        self.seen.clear()


class Session:
    input_format = FORMAT
    compute_device = ComputeDevice.CPU
    supports_partial_updates = True

    def __init__(self, gate: Event | None = None) -> None:
        self.gate = gate
        self.seen: list[bytes] = []
        self.seen_formats: list[AudioFormat] = []
        self.finished = False
        self.closed = False

    def accept_audio(self, chunk: AudioData) -> Sequence[TranscriptUpdate]:
        if self.gate is not None:
            assert self.gate.wait(2)
        self.seen.append(chunk.data)
        self.seen_formats.append(chunk.audio_format)
        return [TranscriptUpdate(0, "hello", TranscriptStatus.PARTIAL)]

    def finish(self) -> Sequence[TranscriptUpdate]:
        self.finished = True
        return [TranscriptUpdate(0, "hello", TranscriptStatus.FINAL)]

    def close(self) -> None:
        self.closed = True


class Engine:
    capabilities: SpeechToTextCapabilities

    def __init__(self, session: Session) -> None:
        self.session = session
        self.open_count = 0

    def open_session(self, options: SpeechToTextOptions) -> Session:
        self.open_count += 1
        return self.session

    def close(self) -> None:
        pass


def test_backlog_warns_recovers_and_preserves_order() -> None:
    backlog = AudioBacklog(FORMAT, warning_ms=20, recovery_ms=5, maximum_ms=40)
    first = AudioData(b"\x01\x00" * 160, FORMAT)
    second = AudioData(b"\x02\x00" * 160, FORMAT)

    assert backlog.put(first) is None
    assert backlog.put(second) == BacklogNotice(BacklogState.WAIT, 20)
    assert backlog.get() == first
    assert backlog.complete(first) is None
    assert backlog.get() == second
    assert backlog.complete(second) == BacklogNotice(BacklogState.READY, 0)
    backlog.close()
    assert backlog.get() is None


def test_backlog_explicitly_fails_without_discarding_existing_audio() -> None:
    backlog = AudioBacklog(FORMAT, warning_ms=5, recovery_ms=0, maximum_ms=10)
    chunk = AudioData(bytes(320), FORMAT)
    backlog.put(chunk)
    with pytest.raises(AudioQueueOverflowError, match="duration limit"):
        backlog.put(chunk)
    assert backlog.get() == chunk


def test_live_pipeline_uses_one_capture_and_keeps_vad_and_stt_independent() -> None:
    data = b"".join(bytes([i, 0]) * 160 for i in (1, 2, 3))
    source = Source([AudioData(data[:100], FORMAT), AudioData(data[100:], FORMAT)])
    detector = Detector([True, False, True])
    session = Session()
    pipeline = LiveSpeechPipeline(
        source,
        FORMAT,
        detector,
        Engine(session),
        start_confirm_ms=1,
        pause_confirm_ms=1,
    )

    with pipeline.open() as stream:
        events = list(stream)

    assert source.capture_count == 1
    assert source.stop_count == 1
    assert b"".join(detector.seen) == data
    assert b"".join(session.seen) == data
    assert len([e for e in events if isinstance(e, SpeechActivityFrame)]) == 3
    assert any(isinstance(e, TranscriptUpdate) for e in events)
    assert session.finished and session.closed


def test_opened_session_reports_its_actual_device() -> None:
    devices: list[ComputeDevice] = []
    pipeline = LiveSpeechPipeline(
        Source([]),
        FORMAT,
        Detector([]),
        Engine(Session()),
        on_compute_device=devices.append,
    )
    with pipeline.open() as stream:
        list(stream)
    assert devices == [ComputeDevice.CPU]


def test_slow_stt_emits_wait_then_ready_without_losing_audio() -> None:
    gate = Event()
    chunks = [AudioData(bytes([i, 0]) * 160, FORMAT) for i in range(4)]
    session = Session(gate)
    pipeline = LiveSpeechPipeline(
        Source(chunks),
        FORMAT,
        Detector([False] * 4),
        Engine(session),
        backlog_warning_ms=20,
        backlog_recovery_ms=5,
        backlog_maximum_ms=100,
    )

    with pipeline.open() as stream:
        first = next(stream)
        assert first == BacklogNotice(BacklogState.WAIT, 20)
        gate.set()
        remainder = list(stream)

    assert BacklogNotice(BacklogState.READY, 0) in remainder
    assert b"".join(session.seen) == b"".join(chunk.data for chunk in chunks)


def test_sustained_stt_lag_fails_visibly() -> None:
    gate = Event()
    chunks = [AudioData(bytes(320), FORMAT) for _ in range(4)]
    pipeline = LiveSpeechPipeline(
        Source(chunks),
        FORMAT,
        Detector([False] * 4),
        Engine(Session(gate)),
        backlog_warning_ms=10,
        backlog_recovery_ms=0,
        backlog_maximum_ms=20,
    )

    with pytest.raises(AudioQueueOverflowError, match="duration limit"):
        with pipeline.open() as stream:
            try:
                list(stream)
            finally:
                gate.set()


def test_early_stop_releases_capture_and_closes_stt_without_finishing() -> None:
    class WaitingSource(Source):
        def __init__(self) -> None:
            super().__init__([])
            self.waiting = Event()
            self.released = Event()

        def capture(self) -> Iterator[AudioData]:
            self.capture_count += 1
            yield AudioData(bytes(320), FORMAT)
            self.waiting.set()
            assert self.released.wait(2)

        def stop_capture(self) -> None:
            super().stop_capture()
            self.released.set()

    source = WaitingSource()
    session = Session()
    pipeline = LiveSpeechPipeline(
        source,
        FORMAT,
        Detector([True]),
        Engine(session),
        start_confirm_ms=1,
    )

    with pipeline.open() as stream:
        assert isinstance(next(stream), SpeechActivityFrame)
        assert source.waiting.wait(2)

    assert source.stop_count == 1
    assert session.closed
    assert not session.finished


def test_external_stop_ends_stream_and_releases_capture() -> None:
    class WaitingSource(Source):
        def __init__(self) -> None:
            super().__init__([])
            self.released = Event()

        def capture(self) -> Iterator[AudioData]:
            yield AudioData(bytes(320), FORMAT)
            assert self.released.wait(2)

        def stop_capture(self) -> None:
            super().stop_capture()
            self.released.set()

    source = WaitingSource()
    session = Session()
    pipeline = LiveSpeechPipeline(
        source,
        FORMAT,
        Detector([True]),
        Engine(session),
        start_confirm_ms=1,
    )

    with pipeline.open() as stream:
        assert isinstance(next(stream), SpeechActivityFrame)
        pipeline.stop()
        assert list(stream) == []

    assert session.closed
    assert source.stop_count >= 1


def test_failed_stt_session_close_is_unsafe_for_recovery() -> None:
    class BrokenSession(Session):
        def close(self) -> None:
            raise RuntimeError("native backend did not close")

    pipeline = LiveSpeechPipeline(
        Source([AudioData(bytes(320), FORMAT)]),
        FORMAT,
        Detector([False]),
        Engine(BrokenSession()),
    )

    with pytest.raises(AudioCaptureStopError, match="STT session did not close"):
        with pipeline.open() as stream:
            list(stream)


def test_vad_and_stt_receive_their_own_sample_rates() -> None:
    source_format = AudioFormat(48000, 1, AudioSampleFormat.INT16)
    stt_format = AudioFormat(8000, 1, AudioSampleFormat.INT16)
    session = Session()
    session.input_format = stt_format
    detector = Detector([False, False])
    pipeline = LiveSpeechPipeline(
        Source([AudioData(bytes(960 * 2), source_format)]),
        source_format,
        detector,
        Engine(session),
    )

    with pipeline.open() as stream:
        list(stream)

    assert len(detector.seen) == 2
    assert session.seen_formats
    assert set(session.seen_formats) == {stt_format}
    assert sum(len(data) for data in session.seen) == 160 * 2


def test_speech_pause_does_not_finish_stt_session() -> None:
    class PausingSource(Source):
        def __init__(self) -> None:
            super().__init__([])
            self.released = Event()

        def capture(self) -> Iterator[AudioData]:
            yield AudioData(bytes(640), FORMAT)
            assert self.released.wait(2)

        def stop_capture(self) -> None:
            self.released.set()

    session = Session()
    pipeline = LiveSpeechPipeline(
        PausingSource(),
        FORMAT,
        Detector([True, False]),
        Engine(session),
        start_confirm_ms=1,
        pause_confirm_ms=1,
    )

    with pipeline.open() as stream:
        transitions = [next(stream), next(stream)]
        assert all(isinstance(event, SpeechActivityFrame) for event in transitions)
        assert not session.finished

    assert session.closed


def test_turn_aware_session_receives_audio_then_boundaries_in_order() -> None:
    class TurnSession(Session):
        def __init__(self) -> None:
            super().__init__()
            self.order: list[str] = []

        def accept_audio(self, chunk: AudioData) -> Sequence[TranscriptUpdate]:
            self.order.append("audio")
            return ()

        def start_turn(self) -> Sequence[TranscriptUpdate]:
            self.order.append("start")
            return ()

        def end_turn(self) -> Sequence[TranscriptUpdate]:
            self.order.append("end")
            return [TranscriptUpdate(0, "hello", TranscriptStatus.FINAL)]

    session = TurnSession()
    source = Source([AudioData(bytes(320 * 3), FORMAT)])
    pipeline = LiveSpeechPipeline(
        source,
        FORMAT,
        Detector([True, True, False]),
        Engine(session),
        start_confirm_ms=1,
        pause_confirm_ms=1,
    )

    with pipeline.open() as stream:
        events = list(stream)

    assert session.order == ["audio", "start", "audio", "audio", "end"]
    assert any(
        isinstance(event, TranscriptUpdate) and event.status is TranscriptStatus.FINAL
        for event in events
    )
    assert session.finished and session.closed
