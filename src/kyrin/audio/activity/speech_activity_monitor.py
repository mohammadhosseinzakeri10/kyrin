"""Smooth VAD decisions while forwarding every audio window immediately."""

from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from enum import StrEnum

from kyrin.audio.activity.voice_activity_detector import VoiceActivityDetector
from kyrin.audio.audio_data import AudioData


class SpeechState(StrEnum):
    """Listening continues in both states."""

    LISTENING = "listening"
    SPEAKING = "speaking"


class SpeechTransition(StrEnum):
    """Confirmed changes in speech activity, not command completion."""

    STARTED = "started"
    PAUSED = "paused"


@dataclass(frozen=True)
class SpeechActivityFrame:
    """The unchanged audio window and its current activity observation."""

    audio: AudioData
    detected_speech: bool | None
    state: SpeechState
    transition: SpeechTransition | None
    speech_started_ns: int | None = field(default=None, compare=False)
    speech_ended_ns: int | None = field(default=None, compare=False)


class SpeechActivityMonitor:
    """Track speech activity without stopping or segmenting the audio stream.

    One monitor owns one VAD instance for one continuous stream. A pause changes
    the activity state only; every audio window remains available downstream.
    """

    def __init__(
        self,
        detector: VoiceActivityDetector,
        *,
        start_confirm_ms: int = 64,
        pause_confirm_ms: int = 384,
    ) -> None:
        if start_confirm_ms <= 0:
            raise ValueError("start_confirm_ms must be positive")
        if pause_confirm_ms <= 0:
            raise ValueError("pause_confirm_ms must be positive")
        if detector.frames_per_window <= 0:
            raise ValueError("detector frames_per_window must be positive")

        self.detector = detector
        self.start_confirm_ms = start_confirm_ms
        self.pause_confirm_ms = pause_confirm_ms
        window_duration_units = detector.frames_per_window * 1000
        sample_rate = detector.input_format.sample_rate
        # Round up: confirmation must span at least the requested duration.
        self._start_windows = (
            start_confirm_ms * sample_rate + window_duration_units - 1
        ) // window_duration_units
        self._pause_windows = (
            pause_confirm_ms * sample_rate + window_duration_units - 1
        ) // window_duration_units
        self._expected_bytes = (
            detector.frames_per_window * detector.input_format.bytes_per_frame
        )
        self.reset()

    @property
    def state(self) -> SpeechState:
        return self._state

    def reset(self) -> None:
        """Start a new audio stream; conversation memory is outside this class."""
        self.detector.reset()
        self._state = SpeechState.LISTENING
        self._speech_run = 0
        self._silence_run = 0
        self._saw_partial = False
        self._speech_started_ns: int | None = None
        self._speech_ended_ns: int | None = None

    def process(self, window: AudioData) -> SpeechActivityFrame:
        """Classify one window and return it immediately with its activity state.

        A final short window remains available to consumers but is not passed
        to a VAD that requires full windows. It does not count as silence.
        """
        if self._saw_partial:
            raise ValueError("new audio after the final partial window requires reset")
        if window.audio_format != self.detector.input_format:
            raise ValueError("audio window format does not match the detector")
        if not window.data:
            raise ValueError("audio window must not be empty")
        if len(window.data) > self._expected_bytes:
            raise ValueError("audio window is larger than the detector window")
        if len(window.data) < self._expected_bytes:
            self._saw_partial = True
            return SpeechActivityFrame(window, None, self._state, None)

        detected_speech = self.detector.detect(window)
        transition = None
        if detected_speech:
            if self._speech_run == 0 and self._state is SpeechState.LISTENING:
                self._speech_started_ns = window.capture_start_ns
            self._speech_ended_ns = window.capture_end_ns
            self._speech_run = min(self._speech_run + 1, self._start_windows)
            self._silence_run = 0
            if (
                self._state is SpeechState.LISTENING
                and self._speech_run >= self._start_windows
            ):
                self._state = SpeechState.SPEAKING
                transition = SpeechTransition.STARTED
        else:
            self._speech_run = 0
            self._silence_run = min(self._silence_run + 1, self._pause_windows)
            if (
                self._state is SpeechState.SPEAKING
                and self._silence_run >= self._pause_windows
            ):
                self._state = SpeechState.LISTENING
                transition = SpeechTransition.PAUSED

        return SpeechActivityFrame(
            window,
            detected_speech,
            self._state,
            transition,
            self._speech_started_ns,
            self._speech_ended_ns,
        )

    def observe(self, windows: Iterable[AudioData]) -> Iterator[SpeechActivityFrame]:
        """Yield one observation per input window without reading ahead."""
        for window in windows:
            yield self.process(window)
