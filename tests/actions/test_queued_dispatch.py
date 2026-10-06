"""Bounded action work stays ordered and does not hold the speech consumer."""

from threading import Event, Thread

import pytest

from kyrin.actions.models import ActionKey, ActionNotice, ActionNoticeReason
from kyrin.actions.queued_dispatch import QueuedActionDispatcher
from kyrin.commands.models import CommandIntent, CommandKind, CommandResolution


def command(segment: int) -> CommandResolution:
    return CommandResolution(
        segment, CommandIntent(CommandKind.OPEN_APP, "telegram"), language="en"
    )


def output_for(item: CommandResolution) -> ActionNotice:
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

    def process(item: CommandResolution) -> tuple[ActionNotice, ...]:
        if item.segment_id == 0:
            started.set()
            assert release.wait(2)
        return (output_for(item),)

    def receive(output: ActionNotice) -> None:
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

    def process(item: CommandResolution) -> tuple[ActionNotice, ...]:
        started.set()
        assert release.wait(2)
        return (output_for(item),)

    def receive(output: ActionNotice) -> None:
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


def test_no_command_is_not_queued_and_worker_cannot_restart() -> None:
    worker = QueuedActionDispatcher(lambda item: (output_for(item),), lambda _: None)
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
            lambda item: (output_for(item),), lambda _: None, max_queued=0
        )
