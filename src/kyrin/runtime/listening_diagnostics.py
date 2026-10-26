"""Bounded in-memory state traces. Never accept speech, audio, or error messages."""

from collections import deque
from threading import Lock
from time import monotonic
from uuid import uuid4


class ListeningDiagnostics:
    def __init__(self) -> None:
        self.session_id = uuid4().hex
        self._lock = Lock()
        self._started = monotonic()
        self._sequence = 0
        self._states: dict[str, str] = {}
        self._pulses: dict[str, tuple[int, float]] = {}
        self._records: deque[str] = deque(maxlen=64)
        self._latest: dict[str, str] = {}

    def state(
        self,
        component: str,
        current: str,
        *,
        reason: str,
        source: str,
        generation: int = 0,
    ) -> None:
        """Arguments must be code-defined labels, never backend/user strings."""
        with self._lock:
            previous = self._states.get(component, "unknown")
            if previous == current:
                return
            self._states[component] = current
            self._sequence += 1
            record = (
                f"{self.session_id} #{self._sequence} "
                f"t={monotonic() - self._started:.3f}s gen={generation} "
                f"{component} {previous}->{current} reason={reason} source={source}"
            )
            self._records.append(record)
            self._latest[component] = record

    def pulse(self, component: str) -> None:
        with self._lock:
            count, _ = self._pulses.get(component, (0, 0.0))
            self._pulses[component] = count + 1, monotonic()

    def snapshot(self) -> tuple[str, ...]:
        with self._lock:
            now = monotonic()
            pulses = " ".join(
                f"{name}={count}/age={now - at:.1f}s"
                for name, (count, at) in sorted(self._pulses.items())
            )
            return (
                *self._records,
                f"{self.session_id} snapshot t={now - self._started:.3f}s",
                *(f"current {record}" for record in self._latest.values()),
                f"{self.session_id} counters {pulses}",
            )
