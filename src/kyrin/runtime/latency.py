"""Bounded content-free latency aggregation using producer timestamps only."""

from collections import deque
from dataclasses import dataclass
from math import ceil
from threading import Lock

from kyrin.actions.models import ActionKey
from kyrin.timing import Temperature, TimingEvent


def _elapsed(start: int | None, end: int | None) -> float | None:
    if start is None or end is None or end < start:
        return None
    return (end - start) / 1_000_000


@dataclass(frozen=True, slots=True)
class StepLatency:
    key: ActionKey
    stamps: tuple[tuple[str, int], ...]

    def duration_ms(self, stage: str) -> float | None:
        """Sum repeated calls (e.g. two model inferences), never their gaps."""
        started = None
        durations = []
        for name, at_ns in self.stamps:
            if name == stage + "_started":
                started = at_ns
            elif name == stage + "_finished":
                duration = _elapsed(started, at_ns)
                if duration is not None:
                    durations.append(duration)
                started = None
        return sum(durations) if durations else None


@dataclass(frozen=True, slots=True)
class ActionLatency:
    session_id: str
    key: ActionKey
    route: str
    temperature: Temperature
    speech_to_final_ms: float | None
    final_to_result_ms: float
    speech_to_result_ms: float | None
    speech_end_to_final_ms: float | None
    final_to_first_feedback_ms: float | None
    understanding_queue_ms: float | None
    action_queue_ms: float | None
    stt_queue_ms: float | None
    steps: tuple[StepLatency, ...]

    @property
    def segment_id(self) -> int:
        return self.key.segment_id


@dataclass(frozen=True, slots=True)
class LatencySummary:
    route: str
    temperature: Temperature
    metric: str
    count: int
    p50_ms: float | None
    p95_ms: float | None


class SpeechActionLatency:
    """At most 16 commands, 256 stamps each, and 512 completed samples.

    Only explicit command completion seals a sample. Raw UI events and late
    events for a sealed command cannot mutate it. IDs include the runtime UUID.
    """

    def __init__(self) -> None:
        self._lock = Lock()
        self._pending: dict[tuple[str, int, int], list[TimingEvent]] = {}
        self._sealed: deque[tuple[str, int, int]] = deque(maxlen=512)
        self._samples: deque[ActionLatency] = deque(maxlen=512)

    def observe(self, event: object) -> ActionLatency | None:
        with self._lock:
            return self._observe(event)

    def _observe(self, event: object) -> ActionLatency | None:
        if not isinstance(event, TimingEvent):
            return None
        identity = (event.session_id, event.key.stream_id, event.key.segment_id)
        if identity in self._sealed:
            return None
        if identity not in self._pending:
            if len(self._pending) >= 16:
                removed = next(iter(self._pending))
                del self._pending[removed]
                self._sealed.append(removed)
            self._pending[identity] = []
        events = self._pending[identity]
        events.append(event)
        if len(events) > 256:
            del self._pending[identity]
            self._sealed.append(identity)
            return None
        if event.stage != "command_completed":
            return None
        del self._pending[identity]
        self._sealed.append(identity)

        def first(stage: str) -> int | None:
            return min(
                (item.at_ns for item in events if item.stage == stage), default=None
            )

        final = first("final")
        total = _elapsed(final, event.at_ns)
        if total is None:
            return None
        keys = sorted({item.key for item in events})
        interpretation = (
            "model"
            if any(item.stage == "inference_started" for item in events)
            else "rules"
            if first("understanding_finished") is not None
            else "unknown"
        )
        sample = ActionLatency(
            event.session_id,
            ActionKey(event.key.stream_id, event.key.segment_id),
            event.route + "/" + interpretation,
            event.temperature,
            _elapsed(first("capture"), final),
            total,
            _elapsed(first("capture"), event.at_ns),
            _elapsed(first("speech_end"), final),
            _elapsed(final, first("feedback")),
            _elapsed(first("understanding_queued"), first("understanding_started")),
            _elapsed(first("action_queued"), first("action_started")),
            _elapsed(first("stt_queued"), first("stt_started")),
            tuple(
                StepLatency(
                    key,
                    tuple(
                        (item.stage, item.at_ns) for item in events if item.key == key
                    ),
                )
                for key in keys
            ),
        )
        self._samples.append(sample)
        return sample

    def summaries(self) -> tuple[LatencySummary, ...]:
        """Nearest-rank percentiles; fewer than 20 samples stay descriptive."""
        groups: dict[tuple[str, Temperature, str], list[float]] = {}
        with self._lock:
            samples = tuple(self._samples)
        for sample in samples:
            metrics = {
                "speech_to_final": sample.speech_to_final_ms,
                "final_to_result": sample.final_to_result_ms,
                "speech_to_result": sample.speech_to_result_ms,
                "speech_end_to_final": sample.speech_end_to_final_ms,
                "first_feedback": sample.final_to_first_feedback_ms,
                "understanding_queue": sample.understanding_queue_ms,
                "action_queue": sample.action_queue_ms,
                "stt_queue": sample.stt_queue_ms,
            }
            for step in sample.steps:
                for stage in (
                    "inference",
                    "dispatch",
                    "postcondition",
                    "stt_final_call",
                ):
                    value = step.duration_ms(stage)
                    if value is not None:
                        # One command remains one statistical sample even for a plan.
                        metrics[stage] = (metrics.get(stage) or 0.0) + value
            for metric, value in metrics.items():
                if value is not None:
                    groups.setdefault(
                        (sample.route, sample.temperature, metric), []
                    ).append(value)
        result = []
        for (route, temperature, metric), values in sorted(groups.items()):
            values.sort()
            count = len(values)
            result.append(
                LatencySummary(
                    route,
                    temperature,
                    metric,
                    count,
                    values[ceil(count * 0.5) - 1] if count >= 20 else None,
                    values[ceil(count * 0.95) - 1] if count >= 20 else None,
                )
            )
        return tuple(result)
