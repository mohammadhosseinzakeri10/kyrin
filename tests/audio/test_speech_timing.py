"""Capture timing survives buffering and is joined at ordered turn boundaries."""

from collections.abc import Sequence
from itertools import count

from kyrin.audio.audio_capture_queue import AudioCaptureQueue
from kyrin.audio.audio_data import AudioData
from kyrin.audio.audio_framer import AudioFramer
from kyrin.audio.live_speech_pipeline import LiveSpeechPipeline
from kyrin.audio.sample_rate_converter import SampleRateConverter
from kyrin.stt.transcript import TranscriptStatus, TranscriptUpdate
from tests.audio.test_live_speech_pipeline import (
    FORMAT,
    Detector,
    Engine,
    Session,
    Source,
)


def test_capture_is_stamped_before_queue_consumption() -> None:
    source = Source([AudioData(bytes(640), FORMAT)])
    times = iter((2_000_000_000,))
    with AudioCaptureQueue(source, clock_ns=lambda: next(times)) as capture:
        chunks = list(capture.chunks())
    assert chunks[0].capture_start_ns == 1_980_000_000
    assert chunks[0].capture_end_ns == 2_000_000_000
    # No consumer-clock call was needed to recover these timestamps.


def test_split_and_join_frames_preserve_sample_positions() -> None:
    chunks = [
        AudioData(bytes(100), FORMAT, 1_000_000_000),
        AudioData(bytes(540), FORMAT, 1_003_125_000),
    ]
    windows = list(AudioFramer(FORMAT, 160).frame(chunks))
    assert [window.capture_start_ns for window in windows] == [
        1_000_000_000,
        1_010_000_000,
    ]
    assert windows[-1].capture_end_ns == 1_020_000_000


def test_resampling_preserves_source_origin_through_filter_flush() -> None:
    chunks = [AudioData(bytes(3200), FORMAT, 1_000_000_000)]
    converted = list(SampleRateConverter(FORMAT, 8000).convert(chunks))
    assert converted[0].capture_start_ns == 1_000_000_000
    assert converted[-1].capture_end_ns == 1_100_000_000
    assert all(
        a.capture_end_ns == b.capture_start_ns
        for a, b in zip(converted, converted[1:], strict=False)
    )


def test_turn_timing_does_not_leak_into_the_next_segment() -> None:
    class TurnSession(Session):
        segment = 0

        def start_turn(self) -> Sequence[TranscriptUpdate]:
            return ()

        def end_turn(self) -> Sequence[TranscriptUpdate]:
            update = TranscriptUpdate(
                self.segment, "private speech", TranscriptStatus.FINAL
            )
            self.segment += 1
            return (update,)

        def accept_audio(self, chunk: AudioData) -> Sequence[TranscriptUpdate]:
            return ()

        def finish(self) -> Sequence[TranscriptUpdate]:
            return ()

    session = TurnSession()
    ticks = count(2_000_000_000, 1_000_000)
    pipeline = LiveSpeechPipeline(
        Source([AudioData(bytes(1280), FORMAT, 1_000_000_000)]),
        FORMAT,
        Detector([True, False, True, False]),
        Engine(session),
        start_confirm_ms=1,
        pause_confirm_ms=1,
        clock_ns=lambda: next(ticks),
    )
    with pipeline.open() as stream:
        updates = [event for event in stream if isinstance(event, TranscriptUpdate)]
    assert len(updates) == 2
    assert all(update.timing is not None for update in updates)
    assert updates[0].timing is not None and updates[1].timing is not None
    first = dict(updates[0].timing.stamps)
    second = dict(updates[1].timing.stamps)
    assert first["capture"] == 1_000_000_000
    assert first["speech_end"] == 1_010_000_000
    assert second["capture"] == 1_020_000_000
    assert second["speech_end"] == 1_030_000_000
    for update in updates:
        assert update.timing is not None
        stamps = dict(update.timing.stamps)
        assert stamps["stt_started"] >= stamps["stt_queued"]
        assert update.emitted_ns == stamps["stt_final_call_finished"]
        assert "private speech" not in repr(update.timing)


def test_unattributed_streaming_final_does_not_guess_speech_boundaries() -> None:
    pipeline = LiveSpeechPipeline(
        Source([AudioData(bytes(320), FORMAT, 1_000_000_000)]),
        FORMAT,
        Detector([True]),
        Engine(Session()),
        start_confirm_ms=1,
    )
    with pipeline.open() as stream:
        updates = [event for event in stream if isinstance(event, TranscriptUpdate)]
    final = updates[-1]
    assert final.status is TranscriptStatus.FINAL
    assert final.emitted_ns is not None and final.timing is not None
    assert "capture" not in dict(final.timing.stamps)
    assert "speech_end" not in dict(final.timing.stamps)
