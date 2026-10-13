"""Bounded, text-free timing of one spoken command through action feedback."""

from collections.abc import Callable
from dataclasses import dataclass
from time import perf_counter_ns

from kyrin.actions.models import ActionFeedback
from kyrin.audio.activity.speech_activity_monitor import (
    SpeechActivityFrame,
    SpeechTransition,
)
from kyrin.runtime.speech_sessions import SpeechSessionEnded
from kyrin.stt.transcript import TranscriptStatus, TranscriptUpdate


@dataclass(frozen=True, slots=True)
class ActionLatency:
    segment_id: int
    speech_to_final_ms: float | None
    final_to_result_ms: float
    speech_to_result_ms: float | None


class SpeechActionLatency:
    """Measure observed event times; never retain audio or transcript text."""

    def __init__(self, clock_ns: Callable[[], int] = perf_counter_ns) -> None:
        self._clock_ns = clock_ns
        self._speech_started_ns: int | None = None
        self._finals: dict[int, tuple[int | None, int]] = {}

    def observe(self, event: object) -> ActionLatency | None:
        if isinstance(event, SpeechSessionEnded):
            self._speech_started_ns = None
            self._finals.clear()
        elif isinstance(event, SpeechActivityFrame):
            if event.transition is SpeechTransition.STARTED:
                self._speech_started_ns = self._clock_ns()
        elif isinstance(event, TranscriptUpdate):
            if event.status is TranscriptStatus.FINAL and event.text.strip():
                self._finals[event.segment_id] = (
                    self._speech_started_ns,
                    self._clock_ns(),
                )
                self._speech_started_ns = None
                if len(self._finals) > 16:
                    self._finals.pop(next(iter(self._finals)))
        elif isinstance(event, ActionFeedback):
            started = self._finals.pop(event.key.segment_id, None)
            if started is not None:
                speech_ns, final_ns = started
                result_ns = self._clock_ns()
                return ActionLatency(
                    event.key.segment_id,
                    (final_ns - speech_ns) / 1_000_000
                    if speech_ns is not None
                    else None,
                    (result_ns - final_ns) / 1_000_000,
                    (result_ns - speech_ns) / 1_000_000
                    if speech_ns is not None
                    else None,
                )
        return None
