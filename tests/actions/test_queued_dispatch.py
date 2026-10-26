"""Bounded action work stays ordered and does not hold the speech consumer."""

from threading import Event, Thread

import pytest

from kyrin.actions.cancellation import ActionExecutionContext
from kyrin.actions.models import (
    ActionFeedback,
    ActionKey,
    ActionNotice,
    ActionNoticeReason,
    ActionOutcome,
    ActionRequest,
    ActionResult,
)
from kyrin.actions.queued_dispatch import (
    ActionOutput,
    FinalActionCommand,
    QueuedActionDispatcher,
)
from kyrin.commands.models import CommandIntent, CommandKind, CommandResolution


def command(segment: int) -> CommandResolution:
    return CommandResolution(
        segment, CommandIntent(CommandKind.OPEN_APP, "telegram"), language="en"
    )


def _append_notice(outputs: list[ActionNotice], item: ActionOutput) -> None:
    assert isinstance(item, ActionNotice)
    outputs.append(item)


def output_for(item: FinalActionCommand) -> ActionNotice:
    assert isinstance(item, CommandResolution)
    assert item.intent is not None
    return ActionNotice(
        ActionKey(item.stream_id, item.segment_id),
        item.intent,
        ActionNoticeReason.NOT_ALLOWED,
        language=item.language,
    )


def test_blocked_action_does_not_block_submit_and_results_keep_order() -> None:
    started = Event()
    release = Event()
    completed = Event()
    outputs: list[ActionNotice] = []

    def process(
        item: FinalActionCommand, _context: ActionExecutionContext
    ) -> tuple[ActionOutput, ...]:
        if item.segment_id == 0:
            started.set()
            assert release.wait(2)
        return (output_for(item),)

    def receive(output: ActionOutput) -> None:
        assert isinstance(output, ActionNotice)
        outputs.append(output)
        if len(outputs) == 2:
            completed.set()

    worker = QueuedActionDispatcher(process, receive, max_queued=1)
    worker.start()
    try:
        assert worker.submit(command(0)) is None
        assert started.wait(1)
        assert worker.submit(command(1)) is None
        busy = worker.submit(command(2))
        assert busy is not None
        assert busy.reason is ActionNoticeReason.BUSY
        assert busy.key.segment_id == 2
        release.set()
        assert completed.wait(2)
    finally:
        release.set()
        worker.close()
    assert [item.key.segment_id for item in outputs] == [0, 1]


def test_close_cancels_queued_command_but_finishes_active_action() -> None:
    started = Event()
    release = Event()
    cancelled = Event()
    outputs: list[ActionNotice] = []

    def process(
        item: FinalActionCommand, _context: ActionExecutionContext
    ) -> tuple[ActionOutput, ...]:
        started.set()
        assert release.wait(2)
        return (output_for(item),)

    def receive(output: ActionOutput) -> None:
        assert isinstance(output, ActionNotice)
        outputs.append(output)
        if output.reason is ActionNoticeReason.CANCELLED:
            cancelled.set()

    worker = QueuedActionDispatcher(process, receive, max_queued=1)
    worker.start()
    assert worker.submit(command(0)) is None
    assert started.wait(1)
    assert worker.submit(command(1)) is None

    closer = Thread(target=worker.close)
    closer.start()
    assert cancelled.wait(1)
    release.set()
    closer.join(2)

    assert not closer.is_alive()
    assert [(item.key.segment_id, item.reason) for item in outputs] == [
        (1, ActionNoticeReason.CANCELLED),
        (0, ActionNoticeReason.NOT_ALLOWED),
    ]
    with pytest.raises(RuntimeError, match="not running"):
        worker.submit(command(2))


def test_natural_close_drains_pending_commands() -> None:
    started = Event()
    release = Event()
    outputs: list[ActionNotice] = []
    errors: list[Exception] = []

    def process(
        item: FinalActionCommand, _context: ActionExecutionContext
    ) -> tuple[ActionOutput, ...]:
        if item.segment_id == 0:
            started.set()
            assert release.wait(2)
        return (output_for(item),)

    worker = QueuedActionDispatcher(
        process, lambda item: _append_notice(outputs, item), max_queued=2
    )
    worker.start()
    assert worker.submit(command(0)) is None
    assert started.wait(1)
    assert worker.submit(command(1)) is None
    assert worker.submit(command(2)) is None

    def close() -> None:
        try:
            worker.close(drain=True, timeout_s=2)
        except Exception as exc:
            errors.append(exc)

    closer = Thread(target=close)
    closer.start()
    release.set()
    closer.join(3)

    assert not closer.is_alive()
    assert errors == []
    assert [(item.key.segment_id, item.reason) for item in outputs] == [
        (0, ActionNoticeReason.NOT_ALLOWED),
        (1, ActionNoticeReason.NOT_ALLOWED),
        (2, ActionNoticeReason.NOT_ALLOWED),
    ]


def test_finite_source_waits_for_queue_capacity_instead_of_dropping_command() -> None:
    started = Event()
    release = Event()
    submitted = Event()
    notices: list[ActionNotice | None] = []
    outputs: list[ActionNotice] = []

    def process(
        item: FinalActionCommand, _context: ActionExecutionContext
    ) -> tuple[ActionOutput, ...]:
        if item.segment_id == 0:
            started.set()
            assert release.wait(2)
        return (output_for(item),)

    worker = QueuedActionDispatcher(
        process, lambda item: _append_notice(outputs, item), max_queued=1
    )
    worker.start()
    assert worker.submit(command(0)) is None
    assert started.wait(1)
    assert worker.submit(command(1)) is None

    def submit_third() -> None:
        notices.append(worker.submit(command(2), wait_for_capacity=True))
        submitted.set()

    submitter = Thread(target=submit_third)
    submitter.start()
    assert not submitted.wait(0.05)
    release.set()
    assert submitted.wait(2)
    submitter.join(1)
    worker.close(drain=True, timeout_s=2)

    assert notices == [None]
    assert [item.key.segment_id for item in outputs] == [0, 1, 2]


def test_generation_change_cancels_unstarted_and_late_old_commands() -> None:
    started = Event()
    release = Event()
    outputs: list[ActionNotice] = []
    processed: list[int] = []

    def process(
        item: FinalActionCommand, _context: ActionExecutionContext
    ) -> tuple[ActionOutput, ...]:
        processed.append(item.segment_id)
        if item.segment_id == 0:
            started.set()
            assert release.wait(2)
        return (output_for(item),)

    worker = QueuedActionDispatcher(
        process, lambda item: _append_notice(outputs, item), max_queued=2
    )
    worker.start()
    generation = worker.generation
    assert worker.submit(command(0), generation=generation) is None
    assert started.wait(1)
    assert worker.submit(command(1), generation=generation) is None

    worker.invalidate_pending()
    late = worker.submit(command(2), generation=generation)
    assert late is not None
    assert late.reason is ActionNoticeReason.CANCELLED
    release.set()
    worker.close(drain=True, timeout_s=2)

    assert processed == [0]
    assert [(item.key.segment_id, item.reason) for item in outputs] == [
        (1, ActionNoticeReason.CANCELLED),
        (0, ActionNoticeReason.NOT_ALLOWED),
    ]


@pytest.mark.parametrize("explicit_generation", (False, True))
def test_generation_change_releases_finite_source_waiting_for_capacity(
    explicit_generation: bool,
) -> None:
    started = Event()
    release = Event()
    submitted = Event()
    notices: list[ActionNotice | None] = []
    outputs: list[ActionNotice] = []

    def process(
        item: FinalActionCommand, _context: ActionExecutionContext
    ) -> tuple[ActionOutput, ...]:
        if item.segment_id == 0:
            started.set()
            assert release.wait(2)
        return (output_for(item),)

    worker = QueuedActionDispatcher(
        process, lambda item: _append_notice(outputs, item), max_queued=1
    )
    worker.start()
    generation = worker.generation
    assert worker.submit(command(0), generation=generation) is None
    assert started.wait(1)
    assert worker.submit(command(1), generation=generation) is None

    def submit_third() -> None:
        notices.append(
            worker.submit(
                command(2),
                wait_for_capacity=True,
                generation=generation if explicit_generation else None,
            )
        )
        submitted.set()

    submitter = Thread(target=submit_third)
    submitter.start()
    assert not submitted.wait(0.05)
    worker.invalidate_pending()
    assert submitted.wait(1)
    release.set()
    submitter.join(1)
    worker.close(drain=True, timeout_s=2)

    assert len(notices) == 1
    assert notices[0] is not None
    assert notices[0].reason is ActionNoticeReason.CANCELLED
    assert [(item.key.segment_id, item.reason) for item in outputs] == [
        (1, ActionNoticeReason.CANCELLED),
        (0, ActionNoticeReason.NOT_ALLOWED),
    ]


def test_drain_deadline_cancels_pending_without_killing_active_action() -> None:
    started = Event()
    release = Event()
    finished = Event()
    outputs: list[ActionNotice] = []

    def process(
        item: FinalActionCommand, _context: ActionExecutionContext
    ) -> tuple[ActionOutput, ...]:
        if item.segment_id == 0:
            started.set()
            assert release.wait(2)
            finished.set()
        return (output_for(item),)

    worker = QueuedActionDispatcher(
        process, lambda item: _append_notice(outputs, item), max_queued=1
    )
    worker.start()
    assert worker.submit(command(0)) is None
    assert started.wait(1)
    assert worker.submit(command(1)) is None
    with pytest.raises(RuntimeError, match="did not stop"):
        worker.close(drain=True, timeout_s=0.01)
    assert (1, ActionNoticeReason.CANCELLED) in [
        (item.key.segment_id, item.reason) for item in outputs
    ]
    release.set()
    assert finished.wait(1)


def test_no_command_is_not_queued_and_worker_cannot_restart() -> None:
    worker = QueuedActionDispatcher(
        lambda item, context: (output_for(item),), lambda _: None
    )
    worker.start()
    try:
        assert worker.submit(CommandResolution(0, None)) is None
    finally:
        worker.close()
    with pytest.raises(RuntimeError, match="cannot be restarted"):
        worker.start()


def test_invalid_capacity_is_rejected() -> None:
    with pytest.raises(ValueError, match="max_queued"):
        QueuedActionDispatcher(
            lambda item, context: (output_for(item),), lambda _: None, max_queued=0
        )


def test_worker_processing_error_reports_unknown_before_close() -> None:
    reported = Event()
    outputs: list[ActionOutput] = []

    def fail(
        _command: FinalActionCommand, _context: ActionExecutionContext
    ) -> tuple[ActionOutput, ...]:
        raise RuntimeError("internal worker failure")

    def receive(output: ActionOutput) -> None:
        outputs.append(output)
        reported.set()

    worker = QueuedActionDispatcher(fail, receive)
    worker.start()
    assert worker.submit(command(0)) is None
    assert reported.wait(1)
    assert len(outputs) == 1
    assert isinstance(outputs[0], ActionFeedback)
    assert outputs[0].outcome is ActionOutcome.UNKNOWN
    assert outputs[0].error_code == "action_worker_failed"
    with pytest.raises(RuntimeError, match="action worker failed"):
        worker.close()


@pytest.mark.parametrize("drain", (False, True))
def test_close_deadline_invalidates_active_plan_context(drain: bool) -> None:
    from kyrin.actions.gate import ActionGate, ActionPolicy
    from kyrin.commands.models import CommandPlan, CommandPlanResolution
    from kyrin.runtime.command_runtime import execute_final_command

    started = Event()
    release = Event()
    completed = Event()
    calls: list[int] = []
    outputs: list[ActionOutput] = []
    contexts: list[ActionExecutionContext] = []

    class Executor:
        def execute(self, request: ActionRequest) -> ActionResult:
            calls.append(request.key.step_index)
            if request.key.step_index == 0:
                started.set()
                assert release.wait(3)
            return ActionResult(request.key, ActionOutcome.LAUNCH_ACCEPTED)

    gate = ActionGate(ActionPolicy(allowed_apps=frozenset({"telegram"})))

    def process(
        item: FinalActionCommand, context: ActionExecutionContext
    ) -> tuple[ActionOutput, ...]:
        contexts.append(context)
        return execute_final_command(item, gate, Executor(), context=context)

    def receive(output: ActionOutput) -> None:
        outputs.append(output)
        if len(outputs) == 2:
            completed.set()

    worker = QueuedActionDispatcher(process, receive)
    worker.start()
    intent = CommandIntent(CommandKind.OPEN_APP, "telegram")
    try:
        worker.submit(CommandPlanResolution(0, CommandPlan((intent, intent))))
        assert started.wait(2)
        with pytest.raises(RuntimeError, match="did not stop"):
            worker.close(drain=drain, timeout_s=0.01)
        assert contexts[0].generation == worker.generation
        assert contexts[0].cancelled
        # The timeout does not kill or roll back the executor already running.
        assert outputs == []
    finally:
        release.set()
        assert completed.wait(2)
    assert calls == [0]
    assert isinstance(outputs[0], ActionFeedback)
    assert outputs[0].outcome is ActionOutcome.LAUNCH_ACCEPTED
    assert isinstance(outputs[1], ActionNotice)
    assert outputs[1].reason is ActionNoticeReason.CANCELLED
    assert outputs[1].key.step_index == 1
