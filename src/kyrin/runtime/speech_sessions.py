"""Bounded recovery of fresh audio/STT sessions without owning dialogue state."""

from collections.abc import Callable, Generator, Iterator
from contextlib import AbstractContextManager
from dataclasses import dataclass, field
from math import isfinite
from threading import Event, Lock
from typing import Protocol

from kyrin.audio.audio_errors import (
    AudioCaptureStopError,
    AudioError,
    AudioQueueOverflowError,
)
from kyrin.audio.live_speech_pipeline import LiveSpeechEvent
from kyrin.audio.microphone.errors import MicrophoneError
from kyrin.stt.errors import DeviceUnavailableError, SpeechToTextError


class SpeechPipeline(Protocol):
    """One attempt; open() must release workers and the STT session on exit."""

    def open(self) -> AbstractContextManager[Iterator[LiveSpeechEvent]]: ...

    def stop(self) -> None:
        """Interrupt pending input and request iteration to end."""
        ...


@dataclass(frozen=True, slots=True)
class SpeechRecoveryPolicy:
    """Total retry budget for one controller, including failures after speech."""

    max_retries: int = 2
    retry_delay_s: float = 1.0

    def __post_init__(self) -> None:
        if self.max_retries < 0:
            raise ValueError("max_retries must not be negative")
        if not isfinite(self.retry_delay_s) or self.retry_delay_s < 0:
            raise ValueError("retry_delay_s must be finite and nonnegative")


@dataclass(frozen=True, slots=True)
class SpeechSessionEnded:
    """Invalidate partial commands before a retry or terminal session end.

    error is diagnostic data, never user-facing text. Consumers may localize
    it with notice_for_error. A None retry delay means no retry is scheduled.
    """

    attempt: int
    error: Exception | None
    retry_delay_s: float | None = None
    session_id: str = field(default="", compare=False)


SpeechRuntimeEvent = LiveSpeechEvent | SpeechSessionEnded


class SpeechSessionController:
    """Run once; create a fresh pipeline/source for every attempt.

    Consume events promptly and close the iterator if abandoning it. stop()
    may be called from another thread and interrupts the retry delay. Engines
    may be shared by the factory; their lifetime remains with the application.
    Normal end-of-input does not restart. Unknown or unsafe errors propagate.
    """

    def __init__(
        self,
        factory: Callable[[], SpeechPipeline],
        policy: SpeechRecoveryPolicy | None = None,
    ) -> None:
        self._factory = factory
        self.policy = policy or SpeechRecoveryPolicy()
        self._stopped = Event()
        self._lock = Lock()
        self._started = False
        self._active: SpeechPipeline | None = None
        self._stop_error: Exception | None = None

    def stop(self) -> None:
        with self._lock:
            if self._stopped.is_set():
                return
            self._stopped.set()
            if self._active is not None:
                try:
                    self._active.stop()
                except Exception as exc:
                    # A stop failure from a timer must reach the consuming thread.
                    self._stop_error = exc

    def events(self) -> Generator[SpeechRuntimeEvent]:
        with self._lock:
            if self._started:
                raise RuntimeError("speech controller can only run once")
            self._started = True
        attempt = 0
        while not self._stopped.is_set():
            failure: Exception | None = None
            abandoned = False
            try:
                pipeline = self._factory()
                with self._lock:
                    if self._stopped.is_set():
                        return
                    self._active = pipeline
                with pipeline.open() as stream:
                    for event in stream:
                        if self._stopped.is_set():
                            break
                        try:
                            yield event
                        except BaseException:
                            # Consumer cancellation/errors must never trigger recovery.
                            abandoned = True
                            raise
            except (
                AudioError,
                SpeechToTextError,
                OSError,
                ValueError,
                RuntimeError,
            ) as exc:
                if abandoned:
                    raise
                failure = exc
            finally:
                with self._lock:
                    self._active = None
                    if self._stop_error is not None:
                        failure = AudioCaptureStopError("speech stop failed")
                        failure.__cause__ = self._stop_error
            retry = (
                failure is not None
                and not self._stopped.is_set()
                and attempt < self.policy.max_retries
                and _can_retry(failure)
            )
            yield SpeechSessionEnded(
                attempt, failure, self.policy.retry_delay_s if retry else None
            )
            if not retry:
                if failure is not None:
                    raise failure
                return
            if self._stopped.wait(self.policy.retry_delay_s):
                return
            attempt += 1


def _can_retry(error: Exception) -> bool:
    if isinstance(error, (AudioCaptureStopError, DeviceUnavailableError)):
        return False
    return isinstance(
        error, (MicrophoneError, AudioQueueOverflowError, SpeechToTextError)
    )
