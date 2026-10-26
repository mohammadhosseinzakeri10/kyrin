"""A short-lived, one-request PCM owner for optional local reprocessing."""

from collections.abc import Callable
from contextlib import AbstractContextManager, nullcontext
from dataclasses import dataclass
from math import isfinite
from threading import Lock, Timer
from time import monotonic

from kyrin.operations import OperationStopped, budget, check_operation
from kyrin.stt.evidence import SpeechHypothesis


@dataclass(frozen=True, slots=True)
class AudioRecoveryPolicy:
    max_pcm_bytes: int = 256_000
    retention_seconds: float = 15.0
    max_reprocess: int = 1
    total_seconds: float = 120.0
    max_pending: int = 5

    def __post_init__(self) -> None:
        if (
            self.max_pcm_bytes <= 0
            or self.max_pcm_bytes % 2
            or not 0 <= self.max_reprocess <= 1
            or self.max_pending < 1
            or any(
                not isfinite(value) or value <= 0
                for value in (self.retention_seconds, self.total_seconds)
            )
        ):
            raise ValueError("invalid audio recovery budget")


class RetainedAudio:
    """No file storage. Close drops ownership, including on late native results.

    A callback must honor the current operation timeout. Python cannot erase
    immutable copies held by a running native/HTTP request; those are released
    when that request returns. Closing never waits for inference.
    """

    def __init__(
        self,
        pcm: bytes,
        infer: Callable[[bytes], SpeechHypothesis | None],
        policy: AudioRecoveryPolicy,
        *,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        if not pcm or len(pcm) > policy.max_pcm_bytes or len(pcm) % 2:
            raise ValueError("whole aligned PCM must fit the recovery budget")
        self._pcm = pcm
        self._infer: Callable[[bytes], SpeechHypothesis | None] | None = infer
        self._admission: Callable[[], AbstractContextManager[None]] = nullcontext
        self._policy = policy
        self._clock = clock
        self._deadline = clock() + policy.retention_seconds
        self._attempts = 0
        self._lock = Lock()
        self._timer = Timer(policy.retention_seconds, self.close)
        self._timer.daemon = True
        self._timer.start()

    @property
    def retained_bytes(self) -> int:
        with self._lock:
            if self._clock() >= self._deadline:
                self._clear()
            return len(self._pcm)

    @property
    def attempts(self) -> int:
        with self._lock:
            return self._attempts

    def _clear(self) -> None:
        self._pcm = b""
        self._infer = None
        self._admission = nullcontext
        self._timer.cancel()

    def close(self) -> None:
        with self._lock:
            self._clear()

    def bind_admission(
        self,
        factory: Callable[[], AbstractContextManager[None]],
    ) -> None:
        """The managed STT adapter binds resource admission before handoff."""
        with self._lock:
            if self._attempts:
                raise RuntimeError("bind admission before using retained audio")
            if self._pcm:
                self._admission = factory

    def reprocess(self) -> SpeechHypothesis | None:
        with self._lock:
            if (
                self._clock() >= self._deadline
                or not self._pcm
                or self._attempts >= self._policy.max_reprocess
            ):
                self._clear()
                return None
            pcm, infer, admission = self._pcm, self._infer, self._admission
            self._attempts += 1  # reserve atomically, before leaving the lock
            seconds = self._deadline - self._clock()
        assert infer is not None
        try:
            with budget(
                min(seconds, self._policy.total_seconds),
                cancelled=lambda: self.retained_bytes == 0,
            ):
                check_operation()
                with admission():
                    result = infer(pcm)
                check_operation()
            with self._lock:
                return result if self._pcm and self._clock() < self._deadline else None
        except OperationStopped:
            return None
        finally:
            self.close()
