"""Recovery must replace a failed stream and never repeat unsafe cleanup."""

from collections.abc import Iterator
from contextlib import contextmanager
from threading import Event, Thread

import pytest

from kyrin.audio.audio_errors import AudioCaptureStopError, AudioQueueOverflowError
from kyrin.runtime.speech_sessions import (
    SpeechRecoveryPolicy,
    SpeechSessionController,
    SpeechSessionEnded,
)
from kyrin.stt.errors import DeviceUnavailableError
from kyrin.stt.transcript import TranscriptStatus, TranscriptUpdate


class FakePipeline:
    def __init__(
        self,
        event: TranscriptUpdate | None = None,
        failure: Exception | None = None,
    ) -> None:
        self.event = event
        self.failure = failure
        self.opened = 0
        self.closed = 0
        self.stopped = 0

    @contextmanager
    def open(self) -> Iterator[Iterator[TranscriptUpdate]]:
        self.opened += 1

        def updates() -> Iterator[TranscriptUpdate]:
            if self.event is not None:
                yield self.event
            if self.failure is not None:
                raise self.failure

        try:
            yield updates()
        finally:
            self.closed += 1

    def stop(self) -> None:
        self.stopped += 1


def test_retries_fresh_pipeline_after_boundary_and_preserves_event_order() -> None:
    partial = TranscriptUpdate(1, "open", TranscriptStatus.PARTIAL)
    final = TranscriptUpdate(1, "open telegram", TranscriptStatus.FINAL)
    first = FakePipeline(partial, AudioQueueOverflowError("full"))
    second = FakePipeline(final)
    created = iter([first, second])
    controller = SpeechSessionController(
        lambda: next(created), SpeechRecoveryPolicy(max_retries=1, retry_delay_s=0)
    )

    events = list(controller.events())

    assert events[0] is partial
    assert isinstance(events[1], SpeechSessionEnded)
    assert events[1].attempt == 0
    assert isinstance(events[1].error, AudioQueueOverflowError)
    assert events[1].retry_delay_s == 0
    assert events[2] is final
    assert events[3] == SpeechSessionEnded(1, None)
    assert first.opened == second.opened == 1
    assert first.closed == second.closed == 1


def test_retry_budget_is_bounded() -> None:
    created: list[FakePipeline] = []

    def factory() -> FakePipeline:
        pipeline = FakePipeline(failure=AudioQueueOverflowError("full"))
        created.append(pipeline)
        return pipeline

    controller = SpeechSessionController(
        factory, SpeechRecoveryPolicy(max_retries=1, retry_delay_s=0)
    )
    events: list[SpeechSessionEnded] = []
    with pytest.raises(AudioQueueOverflowError):
        for event in controller.events():
            assert isinstance(event, SpeechSessionEnded)
            events.append(event)

    assert len(events) == 2
    assert events[0].retry_delay_s == 0
    assert events[1].retry_delay_s is None
    assert len(created) == 2
    assert all(pipeline.closed == 1 for pipeline in created)


@pytest.mark.parametrize(
    "failure", [AudioCaptureStopError("unsafe"), DeviceUnavailableError("gpu")]
)
def test_unsafe_or_unavailable_failure_never_retries(failure: Exception) -> None:
    pipeline = FakePipeline(failure=failure)
    controller = SpeechSessionController(
        lambda: pipeline, SpeechRecoveryPolicy(max_retries=3, retry_delay_s=0)
    )
    events: list[SpeechSessionEnded] = []
    with pytest.raises(type(failure)):
        for event in controller.events():
            assert isinstance(event, SpeechSessionEnded)
            events.append(event)

    assert events == [SpeechSessionEnded(0, failure)]
    assert pipeline.opened == pipeline.closed == 1


def test_stop_interrupts_retry_delay_without_another_factory_call() -> None:
    first = FakePipeline(failure=AudioQueueOverflowError("full"))
    called = 0

    def factory() -> FakePipeline:
        nonlocal called
        called += 1
        return first

    controller = SpeechSessionController(
        factory, SpeechRecoveryPolicy(max_retries=2, retry_delay_s=30)
    )
    stream = controller.events()
    boundary = next(stream)
    assert isinstance(boundary, SpeechSessionEnded)
    assert boundary.retry_delay_s == 30

    controller.stop()
    assert list(stream) == []
    assert called == 1
    assert first.closed == 1


def test_stop_interrupts_active_stream_without_retry() -> None:
    started = Event()
    released = Event()

    class WaitingPipeline(FakePipeline):
        @contextmanager
        def open(self) -> Iterator[Iterator[TranscriptUpdate]]:
            self.opened += 1

            def updates() -> Iterator[TranscriptUpdate]:
                started.set()
                assert released.wait(2)
                yield TranscriptUpdate(1, "late", TranscriptStatus.FINAL)

            try:
                yield updates()
            finally:
                self.closed += 1

        def stop(self) -> None:
            super().stop()
            released.set()

    pipeline = WaitingPipeline()
    controller = SpeechSessionController(lambda: pipeline)
    received: list[object] = []
    worker = Thread(target=lambda: received.extend(controller.events()))
    worker.start()
    assert started.wait(2)
    controller.stop()
    worker.join(2)

    assert not worker.is_alive()
    assert pipeline.stopped == pipeline.closed == 1
    assert received == [SpeechSessionEnded(0, None)]
