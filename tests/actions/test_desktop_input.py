"""Compound input has one FIFO owner, cancellable waiters and safe shutdown."""

from collections.abc import Iterator
from contextlib import contextmanager
from threading import Barrier, Event, Thread
from typing import cast

import pytest

from kyrin.actions.cancellation import ActionCancelled, ActionExecutionContext
from kyrin.actions.desktop_input import DesktopInputBroker, DesktopInputExecutor
from kyrin.actions.gate import ActionGate, ActionPolicy
from kyrin.actions.models import (
    ActionKey,
    ActionNotice,
    ActionNoticeReason,
    ActionOutcome,
    ActionRequest,
    ActionResult,
)
from kyrin.actions.platforms.telegram import ChatVerifier, TelegramSavedMessagesExecutor
from kyrin.actions.queued_dispatch import QueuedActionDispatcher
from kyrin.actions.telegram_verification import ChatSearchChoices, ChatSearchMatch
from kyrin.commands.models import (
    CommandIntent,
    CommandKind,
    CommandPlan,
    CommandPlanResolution,
    CommandResolution,
)
from kyrin.runtime.command_runtime import execute_final_command


def wait_for_waiters(broker: DesktopInputBroker, count: int) -> None:
    # Synchronize at actual FIFO admission, not at thread start or a sleep.
    with broker._condition:
        assert broker._condition.wait_for(lambda: len(broker._waiting) == count, 2)


@contextmanager
def held(broker: DesktopInputBroker) -> Iterator[list[str]]:
    entered = Barrier(2)
    release = Event()
    log: list[str] = []
    errors: list[BaseException] = []

    def operation() -> None:
        log.append("press")
        entered.wait(3)
        assert release.wait(3)
        log.append("release")

    def work() -> None:
        try:
            broker.run(operation)
        except BaseException as exc:
            errors.append(exc)

    thread = Thread(target=work, daemon=True)
    thread.start()
    entered.wait(3)
    try:
        yield log
    finally:
        release.set()
        thread.join(3)
        assert not thread.is_alive()
        assert errors == []


def test_fifo_compound_input_and_nested_delegation_do_not_deadlock() -> None:
    broker = DesktopInputBroker()
    threads: list[Thread] = []
    errors: list[BaseException] = []
    with held(broker) as log:

        def work(index: int) -> None:
            try:
                broker.run(
                    lambda: broker.run(
                        lambda: log.extend((f"{index}:press", f"{index}:release"))
                    )
                )
            except BaseException as exc:
                errors.append(exc)

        for index in range(3):
            thread = Thread(target=work, args=(index,), daemon=True)
            threads.append(thread)
            thread.start()
            wait_for_waiters(broker, index + 1)
        assert log == ["press"]
    for thread in threads:
        thread.join(3)
        assert not thread.is_alive()
    assert errors == []
    assert log == [
        "press",
        "release",
        "0:press",
        "0:release",
        "1:press",
        "1:release",
        "2:press",
        "2:release",
    ]
    broker.close()


def test_cancelled_waiter_exits_before_owner_finishes_and_preserves_fifo() -> None:
    broker = DesktopInputBroker()
    cancel = Event()
    cancelled = Event()
    completed = Event()

    def waiter() -> None:
        try:
            broker.run(
                lambda: pytest.fail("cancelled input ran"), cancelled=cancel.is_set
            )
        except ActionCancelled:
            cancelled.set()

    with held(broker) as log:
        first = Thread(target=waiter, daemon=True)
        second = Thread(target=lambda: broker.run(completed.set), daemon=True)
        first.start()
        wait_for_waiters(broker, 1)
        second.start()
        wait_for_waiters(broker, 2)
        cancel.set()
        assert cancelled.wait(2)
        first.join(2)
        assert not first.is_alive()
        assert not completed.is_set()
        assert log == ["press"]
    second.join(2)
    assert not second.is_alive()
    assert completed.is_set()
    broker.close()


def test_close_rejects_waiting_and_new_input_and_waits_for_active_owner() -> None:
    broker = DesktopInputBroker()
    cancelled = Event()
    closed = Event()
    errors: list[BaseException] = []

    def waiter() -> None:
        try:
            broker.run(lambda: pytest.fail("closed input ran"))
        except ActionCancelled:
            cancelled.set()

    def close() -> None:
        try:
            broker.close(timeout_s=3)
            closed.set()
        except BaseException as exc:
            errors.append(exc)

    with held(broker) as log:
        waiting = Thread(target=waiter, daemon=True)
        waiting.start()
        wait_for_waiters(broker, 1)
        closer = Thread(target=close, daemon=True)
        closer.start()
        assert cancelled.wait(2)
        assert not closed.is_set()
        assert log == ["press"]
        with pytest.raises(ActionCancelled):
            broker.run(lambda: pytest.fail("new input after close ran"))
    waiting.join(2)
    closer.join(2)
    assert not waiting.is_alive() and not closer.is_alive()
    assert closed.is_set() and errors == []
    broker.close()


def test_close_timeout_keeps_owner_and_is_retryable() -> None:
    broker = DesktopInputBroker()
    with held(broker):
        with pytest.raises(RuntimeError, match="did not stop"):
            broker.close(timeout_s=0.01)
        with pytest.raises(ActionCancelled):
            broker.run(lambda: pytest.fail("timeout released input ownership"))
    broker.close()


def test_exception_and_self_close_do_not_strand_owner() -> None:
    broker = DesktopInputBroker()
    with pytest.raises(RuntimeError, match="from its owner"):
        broker.run(broker.close)
    with pytest.raises(ValueError, match="transport"):
        broker.run(lambda: (_ for _ in ()).throw(ValueError("transport")))
    assert broker.run(lambda: "next") == "next"
    broker.close()


@pytest.mark.parametrize("plan", (False, True))
def test_generation_cancellation_reaches_input_waiter_and_releases_gate(
    plan: bool,
) -> None:
    broker = DesktopInputBroker()
    context = ActionExecutionContext(0)
    intent = CommandIntent(CommandKind.OPEN_APP, "telegram")
    gate = ActionGate(ActionPolicy(allowed_apps=frozenset({"telegram"}), max_pending=1))
    outputs: list[object] = []
    errors: list[BaseException] = []
    done = Event()

    class Transport:
        def execute(self, request: ActionRequest) -> ActionResult:
            pytest.fail("cancelled waiter reached transport")

    executor = DesktopInputExecutor(Transport(), broker)

    def work() -> None:
        try:
            command = (
                CommandPlanResolution(1, CommandPlan((intent, intent)))
                if plan
                else CommandResolution(1, intent)
            )
            outputs.extend(
                execute_final_command(command, gate, executor, context=context)
            )
        except BaseException as exc:
            errors.append(exc)
        finally:
            done.set()

    with held(broker):
        thread = Thread(target=work, daemon=True)
        thread.start()
        wait_for_waiters(broker, 1)
        context.cancel()
        assert done.wait(2)
    thread.join(2)
    assert not thread.is_alive()
    assert errors == []
    assert len(outputs) == 1 and isinstance(outputs[0], ActionNotice)
    assert outputs[0].reason is ActionNoticeReason.CANCELLED
    assert isinstance(gate.observe(CommandResolution(2, intent)), ActionRequest)
    broker.close()


def test_action_queue_invalidation_cancels_broker_waiter() -> None:
    broker = DesktopInputBroker()
    intent = CommandIntent(CommandKind.OPEN_APP, "telegram")
    gate = ActionGate(ActionPolicy(allowed_apps=frozenset({"telegram"})))
    outputs: list[object] = []
    delivered = Event()

    class Transport:
        def execute(self, request: ActionRequest) -> ActionResult:
            pytest.fail("invalidated queue reached input transport")

    executor = DesktopInputExecutor(Transport(), broker)

    def receive(output: object) -> None:
        outputs.append(output)
        delivered.set()

    queue = QueuedActionDispatcher(
        lambda command, context: execute_final_command(
            command, gate, executor, context=context
        ),
        receive,
    )
    queue.start()
    try:
        with held(broker):
            assert queue.submit(CommandResolution(1, intent)) is None
            wait_for_waiters(broker, 1)
            queue.invalidate_pending()
            assert delivered.wait(2)
            assert len(outputs) == 1 and isinstance(outputs[0], ActionNotice)
            assert outputs[0].reason is ActionNoticeReason.CANCELLED
    finally:
        queue.close()
        broker.close()


@pytest.mark.parametrize("paging", (False, True))
def test_telegram_waiter_cancels_without_observation_or_input(paging: bool) -> None:
    broker = DesktopInputBroker()
    cancel = Event()
    done = Event()
    errors: list[BaseException] = []

    class Delegate:
        def execute(self, request: ActionRequest) -> ActionResult:
            return ActionResult(request.key, ActionOutcome.LAUNCH_ACCEPTED)

    def identity() -> tuple[str, int]:
        pytest.fail("cancelled waiter must not observe or send input")

    executor = TelegramSavedMessagesExecutor(
        Delegate(),
        telegram_desktop_id="telegram.desktop",
        identity_reader=identity,
        verifier=cast(ChatVerifier, object()),
        input_broker=broker,
    )
    request = ActionRequest(
        ActionKey(0, 1), CommandIntent(CommandKind.OPEN_CHAT, "Alice", "telegram")
    )
    choices = ChatSearchChoices(ChatSearchMatch(40, 80, 50, 20, 800, 600), ())

    def work() -> None:
        try:
            if paging:
                assert (
                    executor.next_search_page(
                        ("telegram.desktop", 12), "Alice", choices, cancel
                    )
                    is None
                )
            else:
                result = executor.complete_selection(
                    request, ("telegram.desktop", 12), "Alice", choices, 1, cancel
                )
                assert result.error_code == "chat_selection_cancelled"
        except BaseException as exc:
            errors.append(exc)
        finally:
            done.set()

    with held(broker):
        thread = Thread(target=work, daemon=True)
        thread.start()
        wait_for_waiters(broker, 1)
        cancel.set()
        assert done.wait(2)
    thread.join(2)
    assert not thread.is_alive()
    assert errors == []
    broker.close()
