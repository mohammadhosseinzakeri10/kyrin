"""Process-local model admission; measured peaks are never inferred from weights.

One native call owns admission until it actually returns, including cleanup.
STT stays resident for its session; other adapters release models before leaving
admission. Priority applies to waiters, not preemption of an active native call.
"""

from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from enum import IntEnum
from pathlib import Path
from threading import Condition
from time import monotonic

from kyrin.operations import check_operation
from kyrin.timing import timed_stage


class Workload(IntEnum):
    STT = 0
    COMMAND = 1
    OCR = 2
    TTS = 3
    DOCUMENT_OCR = 4


class ResourceUnavailable(RuntimeError):
    """Admission refused; no alternate model or device was selected."""


@dataclass(frozen=True)
class PeakMemory:
    """Measured process/model peaks and idle residency for a fixed configuration.

    Include runtime, activations and KV cache, with an appropriate measurement
    margin. Profiles must be invalidated when model/device/context/image changes.
    Values are bytes, not model file sizes. Unknown is represented by no profile.
    """

    ram_bytes: int
    vram_bytes: int
    resident_ram_bytes: int = 0
    resident_vram_bytes: int = 0

    def __post_init__(self) -> None:
        if not (
            0 <= self.resident_ram_bytes <= self.ram_bytes
            and 0 <= self.resident_vram_bytes <= self.vram_bytes
        ):
            raise ValueError("resident memory must fit within measured peak")


@dataclass(frozen=True)
class MemorySnapshot:
    available_ram_bytes: int | None = None
    available_vram_bytes: int | None = None


def system_memory() -> MemorySnapshot:
    """Linux free RAM only. No guessed VRAM or new monitoring dependency."""
    try:
        for line in Path("/proc/meminfo").read_text(encoding="ascii").splitlines():
            if line.startswith("MemAvailable:"):
                return MemorySnapshot(int(line.split()[1]) * 1024)
    except OSError, UnicodeError, ValueError, IndexError:
        pass
    return MemorySnapshot()


@dataclass(frozen=True)
class ResourceLimits:
    ram_bytes: int | None = None
    vram_bytes: int | None = None
    ram_headroom_bytes: int = 512 * 1024**2
    max_waiters: int = 4
    wait_seconds: float = 5.0
    stt_wait_seconds: float = 120.0

    def __post_init__(self) -> None:
        if (
            any(
                value is not None and value <= 0
                for value in (self.ram_bytes, self.vram_bytes)
            )
            or self.ram_headroom_bytes < 0
            or self.max_waiters < 1
            or self.wait_seconds <= 0
            or self.stt_wait_seconds <= 0
        ):
            raise ValueError("invalid model resource limits")


class ModelResources:
    def __init__(
        self,
        limits: ResourceLimits | None = None,
        *,
        peaks: Mapping[str, PeakMemory] | None = None,
        memory: Callable[[], MemorySnapshot] = system_memory,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        self.limits = limits or ResourceLimits()
        self._peaks = dict(peaks or {})
        self._memory = memory
        self._clock = clock
        self._condition = Condition()
        self._waiting: list[tuple[Workload, int]] = []
        self._sequence = 0
        self._active = False
        self._residents: set[str] = set()
        self._blocked = False

    def block(self) -> None:
        """Unconfirmed model cleanup must not admit a competing model."""
        with self._condition:
            self._blocked = True
            self._condition.notify_all()

    def forget(self, key: str) -> None:
        """Called only after the adapter actually releases a resident model."""
        with self._condition:
            self._residents.discard(key)

    def wait_for_waiters(self, count: int, *, timeout: float) -> bool:
        """Bounded observation for deterministic admission diagnostics."""
        with self._condition:
            return self._condition.wait_for(
                lambda: len(self._waiting) >= count, timeout
            )

    def _check_memory(self, key: str) -> None:
        profile = self._peaks.get(key)
        others = [self._peaks.get(name) for name in self._residents if name != key]
        snapshot = self._memory()
        for cap, measured, residents in (
            (
                self.limits.ram_bytes,
                profile.ram_bytes if profile else None,
                [item.resident_ram_bytes if item else None for item in others],
            ),
            (
                self.limits.vram_bytes,
                profile.vram_bytes if profile else None,
                [item.resident_vram_bytes if item else None for item in others],
            ),
        ):
            if cap is not None:
                if measured is None or any(value is None for value in residents):
                    raise ResourceUnavailable(
                        "peak memory is unknown for configured budget"
                    )
                if (
                    measured + sum(value for value in residents if value is not None)
                    > cap
                ):
                    raise ResourceUnavailable(
                        "measured peak exceeds model memory budget"
                    )
        own = profile if key in self._residents else None
        ram_needed = (
            max(0, profile.ram_bytes - (own.resident_ram_bytes if own else 0))
            if profile
            else 0
        )
        vram_needed = (
            max(0, profile.vram_bytes - (own.resident_vram_bytes if own else 0))
            if profile
            else 0
        )
        if (
            snapshot.available_ram_bytes is not None
            and snapshot.available_ram_bytes
            < ram_needed + self.limits.ram_headroom_bytes
        ) or (
            snapshot.available_vram_bytes is not None
            and snapshot.available_vram_bytes < vram_needed
        ):
            raise ResourceUnavailable("insufficient available model memory")

    @contextmanager
    def use(
        self,
        workload: Workload,
        key: str = "default",
        *,
        keep_resident: bool = False,
        cancelled: Callable[[], bool] = lambda: False,
    ) -> Iterator[None]:
        timeout = (
            self.limits.stt_wait_seconds
            if workload is Workload.STT
            else self.limits.wait_seconds
        )
        deadline = self._clock() + timeout
        with timed_stage("model_resource_wait"):
            with self._condition:
                capacity = self.limits.max_waiters + (workload is Workload.STT)
                if len(self._waiting) >= capacity:
                    raise ResourceUnavailable("model resource queue is full")
                ticket = (workload, self._sequence)
                self._sequence += 1
                self._waiting.append(ticket)
                self._condition.notify_all()
                try:
                    while True:
                        check_operation()
                        if self._blocked:
                            raise ResourceUnavailable(
                                "model cleanup is unconfirmed; restart required"
                            )
                        if cancelled() or self._clock() >= deadline:
                            raise ResourceUnavailable(
                                "model resource wait cancelled or timed out"
                            )
                        if not self._active and ticket == min(self._waiting):
                            if keep_resident and self._residents:
                                raise ResourceUnavailable(
                                    "previous STT model is still resident"
                                )
                            self._check_memory(key)
                            self._active = True
                            break
                        self._condition.wait(
                            min(0.05, max(0, deadline - self._clock()))
                        )
                finally:
                    self._waiting.remove(ticket)
                    self._condition.notify_all()
        try:
            with timed_stage("model_resource_run"):
                yield
            if keep_resident:
                with self._condition:
                    self._residents.add(key)
        finally:
            with self._condition:
                self._active = False
                self._condition.notify_all()


# Shared across adapters, previews and shallow audio-file session clones.
MODEL_RESOURCES = ModelResources()
