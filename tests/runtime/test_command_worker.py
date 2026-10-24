"""Deterministic ownership, capacity, stale state, and termination boundaries."""

from collections.abc import Sequence
from threading import Event, Thread

import pytest

from kyrin.commands.coordinator import CommandCoordinator
from kyrin.commands.demo_interpreter import DemoCommandInterpreter
from kyrin.commands.interpreter import Interpretation, ReadyCommand
from kyrin.commands.models import (
    CommandContext,
    CommandEvent,
    CommandIntent,
    CommandKind,
    CommandResolution,
    PendingCommandClarification,
)
from kyrin.runtime.command_worker import (
    CommandUnderstandingWorker,
    CommandWork,
    UnderstoodCommand,
)
from kyrin.stt.transcript import TranscriptStatus, TranscriptUpdate


def _work(segment: int, text: str, *, partial: bool = False) -> CommandWork:
    return CommandWork(
        TranscriptUpdate(
            segment,
            text,
            TranscriptStatus.PARTIAL if partial else TranscriptStatus.FINAL,
            "en",
        ),
        0,
        0,
    )


def _process(
    coordinator: CommandCoordinator, update: TranscriptUpdate, generation: int
) -> tuple[str | None, Sequence[CommandEvent]]:
    return None, coordinator.observe(update)


def test_stream_invalidation_discards_late_state_and_queued_finals() -> None:
    entered = Event()
    release = Event()
    seen: list[tuple[str, str | None]] = []
    results: list[UnderstoodCommand] = []

    class Interpreter:
        def interpret(
            self,
            text: str,
            *,
            language: str | None,
            context: CommandContext,
            pending: PendingCommandClarification | None,
        ) -> Interpretation:
            seen.append((text, context.last_referenced_app))
            if text == "old":
                entered.set()
                assert release.wait(3)
                return ReadyCommand(CommandIntent(CommandKind.OPEN_APP, "telegram"))
            return DemoCommandInterpreter().interpret(
                text, language=language, context=context, pending=pending
            )

    worker = CommandUnderstandingWorker(
        CommandCoordinator(Interpreter()),
        _process,
        results.append,
        lambda: None,
    )
    worker.start()
    try:
        assert worker.submit(_work(0, "old"))
        assert entered.wait(1)
        assert worker.submit(_work(1, "queued old"))
        old_generation = worker.generation
        worker.invalidate(new_stream=True, clear_dialogue=False)
        assert not worker.submit(_work(2, "racing old"), generation=old_generation)
        assert worker.submit(_work(0, "Open browser"))
    finally:
        release.set()
        worker.close(drain=True, timeout_s=2)

    assert seen == [("old", None), ("Open browser", None)]
    assert [result.work.update.text for result in results] == ["Open browser"]
    assert results[0].decisions == (
        CommandResolution(
            0,
            CommandIntent(CommandKind.OPEN_APP, "browser"),
            stream_id=1,
            language="en",
        ),
    )


def test_bounded_fifo_rejects_overload_and_gives_finals_preview_capacity() -> None:
    entered = Event()
    release = Event()
    seen: list[str] = []
    results: list[UnderstoodCommand] = []

    def process(
        coordinator: CommandCoordinator, update: TranscriptUpdate, generation: int
    ) -> tuple[str | None, Sequence[CommandEvent]]:
        seen.append(update.text)
        if update.segment_id == 0:
            entered.set()
            assert release.wait(3)
        return _process(coordinator, update, generation)

    worker = CommandUnderstandingWorker(
        CommandCoordinator(DemoCommandInterpreter()),
        process,
        results.append,
        lambda: None,
        max_queued=2,
    )
    worker.start()
    try:
        assert worker.submit(_work(0, "Open Telegram"))
        assert entered.wait(1)
        assert worker.submit(_work(1, "preview", partial=True))
        assert worker.submit(_work(1, "Open browser"))
        assert worker.submit(_work(2, "Open Telegram"))
        assert not worker.submit(_work(3, "rejected"))
        assert not worker.submit(_work(3, "preview", partial=True))
    finally:
        release.set()
        worker.close(drain=True, timeout_s=2)
    assert seen == ["Open Telegram", "Open browser", "Open Telegram"]
    assert [result.work.update.segment_id for result in results] == [0, 1, 2]
    with pytest.raises(RuntimeError, match="cannot be restarted"):
        worker.start()


def test_close_reports_live_inference_then_joins_after_it_returns() -> None:
    entered = Event()
    release = Event()
    results: list[UnderstoodCommand] = []

    def process(
        coordinator: CommandCoordinator, update: TranscriptUpdate, generation: int
    ) -> tuple[str | None, Sequence[CommandEvent]]:
        entered.set()
        assert release.wait(3)
        return _process(coordinator, update, generation)

    worker = CommandUnderstandingWorker(
        CommandCoordinator(DemoCommandInterpreter()),
        process,
        results.append,
        lambda: None,
    )
    worker.start()
    assert worker.submit(_work(0, "Open Telegram"))
    assert entered.wait(1)
    try:
        with pytest.raises(
            RuntimeError, match="in-flight inference may still be running"
        ):
            worker.close(drain=False, timeout_s=0.01)
        assert worker._thread is not None and worker._thread.is_alive()
        assert not worker.submit(_work(1, "Open browser"))
        assert results == []
    finally:
        release.set()
        worker.close(drain=False, timeout_s=2)
    assert not worker._thread.is_alive()
    assert results == []


def test_finite_capacity_wait_is_woken_by_invalidation() -> None:
    entered = Event()
    release = Event()
    submitted = Event()
    accepted: list[bool] = []
    results: list[UnderstoodCommand] = []

    def process(
        coordinator: CommandCoordinator, update: TranscriptUpdate, generation: int
    ) -> tuple[str | None, Sequence[CommandEvent]]:
        entered.set()
        assert release.wait(3)
        return _process(coordinator, update, generation)

    worker = CommandUnderstandingWorker(
        CommandCoordinator(DemoCommandInterpreter()),
        process,
        results.append,
        lambda: None,
        max_queued=1,
    )
    worker.start()
    assert worker.submit(_work(0, "Open Telegram"))
    assert entered.wait(1)
    assert worker.submit(_work(1, "Open browser"))
    generation = worker.generation

    def submit() -> None:
        submitted.set()
        accepted.append(
            worker.submit(
                _work(2, "Open Telegram"),
                wait_for_capacity=True,
                generation=generation,
            )
        )

    producer = Thread(target=submit)
    producer.start()
    try:
        assert submitted.wait(1)
        worker.invalidate()
        producer.join(1)
        assert not producer.is_alive()
        assert accepted == [False]
    finally:
        release.set()
        producer.join(2)
        worker.close(drain=False, timeout_s=2)
    assert results == []


@pytest.mark.parametrize("failure", ("process", "callback"))
def test_worker_failure_is_reported_and_pending_work_does_not_run(failure: str) -> None:
    entered = Event()
    release = Event()
    failed = Event()
    error = ValueError("adapter failed")
    calls: list[str] = []

    def process(
        coordinator: CommandCoordinator, update: TranscriptUpdate, generation: int
    ) -> tuple[str | None, Sequence[CommandEvent]]:
        calls.append(update.text)
        entered.set()
        assert release.wait(3)
        if failure == "process":
            raise error
        return _process(coordinator, update, generation)

    def receive(result: UnderstoodCommand) -> None:
        raise error

    worker = CommandUnderstandingWorker(
        CommandCoordinator(DemoCommandInterpreter()),
        process,
        receive,
        failed.set,
    )
    worker.start()
    assert worker.submit(_work(0, "Open Telegram"))
    assert entered.wait(1)
    assert worker.submit(_work(1, "Open browser"))
    release.set()
    assert failed.wait(1)
    with pytest.raises(RuntimeError, match="understanding worker failed") as raised:
        worker.close(drain=False, timeout_s=2)
    assert raised.value.__cause__ is error
    assert calls == ["Open Telegram"]
    assert worker._thread is not None and not worker._thread.is_alive()


def test_coordinator_fork_does_not_share_mutable_fragments() -> None:
    coordinator = CommandCoordinator(DemoCommandInterpreter())
    coordinator.observe(_work(0, "Open").update)
    discarded = coordinator.fork()
    discarded.observe(_work(1, "Telegram").update)
    assert coordinator.last_referenced_app is None
    result = coordinator.observe(_work(1, "browser").update)
    assert result == (
        CommandResolution(
            1, CommandIntent(CommandKind.OPEN_APP, "browser"), language="en"
        ),
    )


@pytest.mark.parametrize("stop_phase", ("before_close", "during_close"))
def test_stop_shortens_existing_or_future_eof_drain(stop_phase: str) -> None:
    entered = Event()
    release = Event()
    results: list[UnderstoodCommand] = []
    errors: list[Exception] = []

    def process(
        coordinator: CommandCoordinator, update: TranscriptUpdate, generation: int
    ) -> tuple[str | None, Sequence[CommandEvent]]:
        entered.set()
        assert release.wait(5)
        return _process(coordinator, update, generation)

    worker = CommandUnderstandingWorker(
        CommandCoordinator(DemoCommandInterpreter()),
        process,
        results.append,
        lambda: None,
    )
    worker.start()
    assert worker.submit(_work(0, "Open Telegram"))
    assert entered.wait(1)
    if stop_phase == "before_close":
        worker.request_stop()

    def close() -> None:
        try:
            worker.close(drain=True, timeout_s=30)
        except Exception as exc:
            errors.append(exc)

    closer = Thread(target=close)
    closer.start()
    try:
        if stop_phase == "during_close":
            with worker._condition:
                assert worker._condition.wait_for(lambda: worker._closed, 1)
            worker.request_stop()
        closer.join(2)
        assert not closer.is_alive(), "stop waited for the long EOF drain budget"
        assert len(errors) == 1
        assert "in-flight inference may still be running" in str(errors[0])
        assert worker._thread is not None and worker._thread.is_alive()
    finally:
        release.set()
        closer.join(3)
        worker.close(drain=False, timeout_s=2)
    assert not worker._thread.is_alive()
    assert results == []
