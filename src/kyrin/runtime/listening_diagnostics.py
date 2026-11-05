"""Bounded in-memory state traces. Never accept speech, audio, or error messages."""

from collections import deque
from collections.abc import Callable
from threading import Lock
from time import monotonic
from uuid import uuid4


class ListeningDiagnostics:
    def __init__(self, *, clock: Callable[[], float] = monotonic) -> None:
        self.session_id = uuid4().hex
        self._clock = clock
        self._lock = Lock()
        self._started = clock()
        self._sequence = 0
        self._states: dict[str, tuple[str, int]] = {}
        self._pulses: dict[str, tuple[int, float]] = {}
        self._records: deque[str] = deque(maxlen=64)
        self._latest: dict[str, str] = {}
        self._changed_at: dict[str, float] = {}
        self._queues: dict[str, tuple[int, int, str, int]] = {}
        self._providers: dict[str, Callable[[], tuple[str, ...]]] = {}

    def attach(self, name: str, snapshot: Callable[[], tuple[str, ...]]) -> None:
        """Attach a fixed, content-free component snapshot, never user labels."""
        with self._lock:
            self._providers[name] = snapshot

    def queue(self, name: str, pending: int, limit: int, unit: str) -> None:
        with self._lock:
            high = self._queues.get(name, (0, 0, unit, 0))[3]
            self._queues[name] = pending, limit, unit, max(high, pending)

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
            previous = self._states.get(component, ("unknown", 0))[0]
            if self._states.get(component) == (current, generation):
                return
            self._states[component] = current, generation
            now = self._clock()
            self._changed_at[component] = now
            self._sequence += 1
            record = (
                f"{self.session_id} #{self._sequence} "
                f"t={now - self._started:.3f}s gen={generation} "
                f"{component} {previous}->{current} reason={reason} source={source}"
            )
            self._records.append(record)
            self._latest[component] = record

    def pulse(self, component: str) -> None:
        with self._lock:
            count, _ = self._pulses.get(component, (0, 0.0))
            self._pulses[component] = count + 1, self._clock()

    def snapshot(self) -> tuple[str, ...]:
        with self._lock:
            now = self._clock()
            pulses = " ".join(
                f"{name}={count}/age={now - at:.1f}s"
                for name, (count, at) in sorted(self._pulses.items())
            )
            providers = tuple(self._providers.items())
            result = (
                *self._records,
                f"{self.session_id} snapshot t={now - self._started:.3f}s",
                *(
                    f"current {record} age={now - self._changed_at[name]:.3f}s"
                    for name, record in self._latest.items()
                ),
                *(
                    f"queue {name} pending={pending} limit={limit} "
                    f"unit={unit} high={high}"
                    for name, (pending, limit, unit, high) in self._queues.items()
                ),
                f"{self.session_id} counters {pulses}",
            )
        # Never nest the diagnostic lock with a worker/resource lock.
        return (
            *result,
            *(f"{name} {line}" for name, provider in providers for line in provider()),
        )
