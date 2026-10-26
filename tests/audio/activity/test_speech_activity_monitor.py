"""Speech activity must remain observable throughout a continuous stream."""

from collections.abc import Iterator

import pytest

from kyrin.audio.activity.silero_vad import SileroVad
from kyrin.audio.activity.speech_activity_monitor import (
    SpeechActivityMonitor,
    SpeechState,
    SpeechTransition,
)
from kyrin.audio.audio_data import AudioData
from kyrin.audio.audio_format import AudioFormat, AudioSampleFormat
from kyrin.audio.audio_framer import AudioFramer

FORMAT = AudioFormat(16000, 1, AudioSampleFormat.INT16)
WINDOW_SAMPLES = 160  # 10 ms at 16 kHz


class SequenceVad:
    input_format = FORMAT
    frames_per_window = WINDOW_SAMPLES

    def __init__(self, decisions: list[bool]) -> None:
        self.decisions = iter(decisions)
        self.reset_count = 0
        self.detect_count = 0

    def detect(self, window: AudioData) -> bool:
        self.detect_count += 1
        return next(self.decisions)

    def reset(self) -> None:
        self.reset_count += 1


def window() -> AudioData:
    return AudioData(bytes(WINDOW_SAMPLES * FORMAT.bytes_per_frame), FORMAT)


def test_continuous_frames_and_stable_transitions() -> None:
    decisions = [
        False,
        True,
        False,
        True,
        True,
        False,
        True,
        False,
        False,
        False,
        True,
        True,
    ]
    vad = SequenceVad(decisions)
    monitor = SpeechActivityMonitor(vad, start_confirm_ms=20, pause_confirm_ms=30)
    audio = [window() for _ in decisions]

    results = list(monitor.observe(audio))

    assert [result.audio for result in results] == audio
    assert [result.detected_speech for result in results] == decisions
    assert [result.transition for result in results] == [
        None,
        None,
        None,
        None,
        SpeechTransition.STARTED,
        None,
        None,
        None,
        None,
        SpeechTransition.PAUSED,
        None,
        SpeechTransition.STARTED,
    ]
    assert results[9].state is SpeechState.LISTENING
    assert results[-1].state is SpeechState.SPEAKING
    assert vad.detect_count == len(audio)


def test_monitor_emits_each_frame_without_reading_ahead() -> None:
    monitor = SpeechActivityMonitor(SequenceVad([True]), start_confirm_ms=10)

    def source() -> Iterator[AudioData]:
        yield window()
        raise AssertionError("monitor waited for the rest of the stream")

    first = next(monitor.observe(source()))

    assert first.transition is SpeechTransition.STARTED
    assert first.audio == window()


def test_framer_remainder_is_forwarded_without_vad_classification() -> None:
    vad = SequenceVad([True])
    monitor = SpeechActivityMonitor(vad, start_confirm_ms=10)
    data = bytes(WINDOW_SAMPLES * 2 + 8)
    chunks = [AudioData(data[:12], FORMAT), AudioData(data[12:], FORMAT)]
    framed = AudioFramer(FORMAT, WINDOW_SAMPLES).frame(chunks)

    results = list(monitor.observe(framed))

    assert b"".join(result.audio.data for result in results) == data
    assert results[0].transition is SpeechTransition.STARTED
    assert results[1].detected_speech is None
    assert results[1].transition is None
    assert results[1].state is SpeechState.SPEAKING
    assert vad.detect_count == 1

    with pytest.raises(ValueError, match="final partial"):
        monitor.process(window())


def test_real_silero_and_monitor_accept_framed_silence() -> None:
    detector = SileroVad()
    monitor = SpeechActivityMonitor(detector)
    chunk = AudioData(bytes(detector.frames_per_window * 2 * 2), detector.input_format)
    framed = AudioFramer(detector.input_format, detector.frames_per_window).frame(
        [chunk]
    )

    observations = list(monitor.observe(framed))

    assert len(observations) == 2
    assert all(item.detected_speech is False for item in observations)
    assert all(item.state is SpeechState.LISTENING for item in observations)


def test_reset_clears_only_audio_activity_state() -> None:
    vad = SequenceVad([True, True])
    monitor = SpeechActivityMonitor(vad, start_confirm_ms=10)

    assert monitor.process(window()).state is SpeechState.SPEAKING
    monitor.reset()

    assert monitor.state is SpeechState.LISTENING
    assert monitor.process(window()).transition is SpeechTransition.STARTED
    assert vad.reset_count == 2


def test_confirmation_duration_rounds_up_to_whole_windows() -> None:
    monitor = SpeechActivityMonitor(
        SequenceVad([True, True, True]), start_confirm_ms=25
    )

    assert monitor.process(window()).transition is None
    assert monitor.process(window()).transition is None
    assert monitor.process(window()).transition is SpeechTransition.STARTED


def test_640_ms_mid_sentence_gap_only_pauses_short_threshold() -> None:
    decisions = [True, *([False] * 64), True]
    short = SpeechActivityMonitor(
        SequenceVad(decisions), start_confirm_ms=10, pause_confirm_ms=384
    )
    long = SpeechActivityMonitor(
        SequenceVad(decisions), start_confirm_ms=10, pause_confirm_ms=800
    )

    short_transitions = [
        frame.transition for frame in short.observe(window() for _ in decisions)
    ]
    long_transitions = [
        frame.transition for frame in long.observe(window() for _ in decisions)
    ]

    assert short_transitions.count(SpeechTransition.PAUSED) == 1
    assert short_transitions.count(SpeechTransition.STARTED) == 2
    assert long_transitions.count(SpeechTransition.PAUSED) == 0
    assert long_transitions.count(SpeechTransition.STARTED) == 1


def test_monitor_rejects_invalid_windows_and_config() -> None:
    vad = SequenceVad([])
    monitor = SpeechActivityMonitor(vad)
    wrong_format = AudioFormat(8000, 1, AudioSampleFormat.INT16)

    with pytest.raises(ValueError, match="format"):
        monitor.process(AudioData(bytes(320), wrong_format))
    with pytest.raises(ValueError, match="window"):
        monitor.process(AudioData(bytes(322), FORMAT))
    with pytest.raises(ValueError, match="empty"):
        monitor.process(AudioData(b"", FORMAT))
    assert vad.detect_count == 0

    with pytest.raises(ValueError, match="start_confirm_ms"):
        SpeechActivityMonitor(vad, start_confirm_ms=0)
    with pytest.raises(ValueError, match="pause_confirm_ms"):
        SpeechActivityMonitor(vad, pause_confirm_ms=0)
