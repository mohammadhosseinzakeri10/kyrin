"""Attach producer timing to STT updates without keeping content or guessing turns."""

from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from time import perf_counter_ns

from kyrin.audio.activity.speech_activity_monitor import (
    SpeechActivityFrame,
    SpeechTransition,
)
from kyrin.audio.audio_backlog import BacklogMarker
from kyrin.stt.transcript import TranscriptStatus, TranscriptTiming, TranscriptUpdate


@dataclass(frozen=True)
class TimedSpeechBoundary:
    marker: BacklogMarker
    frame: SpeechActivityFrame
    queued_ns: int


class SpeechTiming:
    def __init__(self, clock_ns: Callable[[], int] = perf_counter_ns) -> None:
        self.clock_ns = clock_ns
        self.start_ns: int | None = None
        self.end_ns: int | None = None
        self.queued_ns: int | None = None
        self.dequeued_ns: int | None = None

    def boundary(
        self, frame: SpeechActivityFrame, queued_ns: int | None = None
    ) -> None:
        if frame.transition is SpeechTransition.STARTED:
            self.start_ns = frame.speech_started_ns
            self.end_ns = None
            self.queued_ns = self.dequeued_ns = None
        elif frame.transition is SpeechTransition.PAUSED:
            self.end_ns = frame.speech_ended_ns
            self.queued_ns = queued_ns
            self.dequeued_ns = self.clock_ns() if queued_ns is not None else None

    def call(
        self, callback: Callable[[], Sequence[TranscriptUpdate]]
    ) -> tuple[TranscriptUpdate, ...]:
        started = self.clock_ns()
        updates = callback()
        finished = self.clock_ns()
        result = []
        for update in updates:
            stamps = [
                ("stt_final_call_started", started),
                ("stt_final_call_finished", finished),
            ]
            if self.queued_ns is not None and self.dequeued_ns is not None:
                stamps.extend(
                    (("stt_queued", self.queued_ns), ("stt_started", self.dequeued_ns))
                )
            if self.start_ns is not None:
                stamps.append(("capture", self.start_ns))
            if self.end_ns is not None:
                stamps.append(("speech_end", self.end_ns))
            result.append(
                replace(
                    update, emitted_ns=finished, timing=TranscriptTiming(tuple(stamps))
                )
            )
            if update.status is TranscriptStatus.FINAL:
                # A later turn cannot inherit this turn's audio attribution.
                self.start_ns = self.end_ns = None
                self.queued_ns = self.dequeued_ns = None
        return tuple(result)
