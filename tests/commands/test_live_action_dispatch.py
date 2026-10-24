"""Final live decisions reach only explicitly allowed, injected actions."""

from collections.abc import Sequence
from pathlib import Path
from runpy import run_path
from threading import Event

import pytest

from kyrin.actions.gate import ActionGate, ActionPolicy
from kyrin.actions.models import (
    ActionFeedback,
    ActionNotice,
    ActionNoticeReason,
    ActionOutcome,
    ActionRequest,
    ActionResult,
)
from kyrin.actions.queued_dispatch import QueuedActionDispatcher
from kyrin.commands.coordinator import CommandCoordinator
from kyrin.commands.demo_interpreter import DemoCommandInterpreter
from kyrin.commands.models import (
    CommandEvent,
    CommandIntent,
    CommandKind,
    CommandPlanResolution,
    CommandResolution,
)
from kyrin.runtime.command_runtime import dispatch_command_action, execute_final_command
from kyrin.stt.transcript import TranscriptStatus, TranscriptUpdate

SCRIPT = Path(__file__).resolve().parents[2] / "scripts/audio/check_live_speech.py"
NAMESPACE = run_path(str(SCRIPT))
parse_args = NAMESPACE["parse_args"]


class FakeExecutor:
    def __init__(self, outcomes: tuple[ActionOutcome, ...]) -> None:
        self.outcomes = outcomes
        self.calls: list[ActionRequest] = []

    def execute(self, request: ActionRequest) -> ActionResult:
        outcome = self.outcomes[len(self.calls)]
        self.calls.append(request)
        if outcome in (ActionOutcome.FAILED, ActionOutcome.UNKNOWN):
            return ActionResult(request.key, outcome, error_code="test_failure")
        return ActionResult(request.key, outcome)


def gate(*, apps: frozenset[str] = frozenset({"telegram"})) -> ActionGate:
    return ActionGate(
        ActionPolicy(
            allowed_apps=apps,
            supported_kinds=frozenset({CommandKind.OPEN_APP}),
        )
    )


def decisions(
    text: str, status: TranscriptStatus, *, segment: int = 0
) -> Sequence[CommandEvent]:
    return CommandCoordinator(DemoCommandInterpreter()).observe(
        TranscriptUpdate(segment, text, status, "en")
    )


def test_only_final_allowlisted_app_launches_once() -> None:
    coordinator = CommandCoordinator(DemoCommandInterpreter())
    action_gate = gate()
    executor = FakeExecutor((ActionOutcome.LAUNCH_ACCEPTED,))

    partial = coordinator.observe(
        TranscriptUpdate(0, "Open Telegram", TranscriptStatus.PARTIAL, "en")
    )
    assert all(
        not dispatch_command_action(event, action_gate, executor) for event in partial
    )
    assert not executor.calls

    final = coordinator.observe(
        TranscriptUpdate(0, "Open Telegram", TranscriptStatus.FINAL, "en")
    )
    output = tuple(
        action
        for event in final
        for action in dispatch_command_action(event, action_gate, executor)
    )
    assert len(executor.calls) == 1
    assert len(output) == 1
    assert isinstance(output[0], ActionFeedback)
    assert output[0].outcome is ActionOutcome.LAUNCH_ACCEPTED
    assert not dispatch_command_action(final[0], action_gate, executor)
    assert len(executor.calls) == 1


def test_negated_final_and_unclear_final_never_launch() -> None:
    action_gate = gate()
    executor = FakeExecutor(())
    for phrase in ("Do not open Telegram", "to open Telegram"):
        for event in decisions(phrase, TranscriptStatus.FINAL):
            assert not dispatch_command_action(event, action_gate, executor)
    assert not executor.calls


def test_partial_open_replaced_by_final_negation_never_launches() -> None:
    coordinator = CommandCoordinator(DemoCommandInterpreter())
    action_gate = gate()
    executor = FakeExecutor(())
    for event in coordinator.observe(
        TranscriptUpdate(0, "Open Telegram", TranscriptStatus.PARTIAL, "en")
    ):
        assert not dispatch_command_action(event, action_gate, executor)
    for event in coordinator.observe(
        TranscriptUpdate(0, "Do not open Telegram", TranscriptStatus.FINAL, "en")
    ):
        assert not dispatch_command_action(event, action_gate, executor)
    assert not executor.calls


def test_unconfigured_app_is_blocked() -> None:
    action_gate = gate(apps=frozenset({"browser"}))
    executor = FakeExecutor(())
    event = decisions("Open Telegram", TranscriptStatus.FINAL)[0]

    output = dispatch_command_action(event, action_gate, executor)

    assert len(output) == 1
    assert isinstance(output[0], ActionNotice)
    assert output[0].reason is ActionNoticeReason.NOT_ALLOWED
    assert not executor.calls


def test_plan_launches_first_app_then_reports_unsupported_chat() -> None:
    action_gate = gate()
    executor = FakeExecutor((ActionOutcome.LAUNCH_ACCEPTED,))
    event = decisions("Open Telegram and open Alice chat", TranscriptStatus.FINAL)[0]

    output = dispatch_command_action(event, action_gate, executor)

    assert len(executor.calls) == 1
    assert isinstance(output[0], ActionFeedback)
    assert output[0].outcome is ActionOutcome.LAUNCH_ACCEPTED
    assert isinstance(output[1], ActionNotice)
    assert output[1].reason is ActionNoticeReason.UNSUPPORTED
    assert not dispatch_command_action(event, action_gate, executor)


def test_failed_first_step_allows_independent_second_app() -> None:
    action_gate = gate(apps=frozenset({"telegram", "browser"}))
    executor = FakeExecutor((ActionOutcome.FAILED, ActionOutcome.LAUNCH_ACCEPTED))
    event = decisions("Open Telegram and open browser", TranscriptStatus.FINAL)[0]

    output = dispatch_command_action(event, action_gate, executor)

    assert len(output) == 2
    assert isinstance(output[0], ActionFeedback)
    assert output[0].outcome is ActionOutcome.FAILED
    assert len(executor.calls) == 2
    assert isinstance(output[1], ActionFeedback)
    assert output[1].outcome is ActionOutcome.LAUNCH_ACCEPTED


def test_real_execution_requires_commands_mode_and_explicit_app_binding() -> None:
    base = ["--model-path", "/tmp/model", "--language", "en"]
    with pytest.raises(SystemExit):
        parse_args([*base, "--execute-actions"])
    with pytest.raises(SystemExit):
        parse_args([*base, "--mode", "commands", "--execute-actions"])
    with pytest.raises(SystemExit):
        parse_args(
            [*base, "--mode", "commands", "--launch-app", "telegram=/tmp/a.desktop"]
        )
    with pytest.raises(SystemExit):
        parse_args(
            [
                *base,
                "--mode",
                "commands",
                "--execute-actions",
                "--launch-app",
                "telegram=relative.desktop",
            ]
        )

    args = parse_args(
        [
            "--mode",
            "commands",
            "--model-path",
            "/tmp/model",
            "--language",
            "en",
            "--execute-actions",
            "--launch-app",
            "telegram=/tmp/a.desktop",
        ]
    )
    assert args.launch_apps == {"telegram": Path("/tmp/a.desktop")}


def test_default_remains_dry_run() -> None:
    action_gate = gate()
    event = decisions("Open Telegram", TranscriptStatus.FINAL)[0]

    output = dispatch_command_action(event, action_gate, None)

    assert len(output) == 1
    assert isinstance(output[0], ActionRequest)


def test_queued_plan_reports_first_launch_and_unsupported_next_step() -> None:
    action_gate = gate()
    executor = FakeExecutor((ActionOutcome.LAUNCH_ACCEPTED,))
    received: list[ActionNotice | ActionFeedback] = []
    completed = Event()

    def on_output(output: ActionNotice | ActionFeedback) -> None:
        received.append(output)
        if len(received) == 2:
            completed.set()

    worker = QueuedActionDispatcher(
        lambda item, context: execute_final_command(
            item, action_gate, executor, context=context
        ),
        on_output,
    )
    worker.start()
    try:
        event = decisions("Open Telegram and open Alice chat", TranscriptStatus.FINAL)[
            0
        ]
        assert isinstance(event, (CommandResolution, CommandPlanResolution))
        assert worker.submit(event) is None
        assert completed.wait(2)
    finally:
        worker.close()

    assert len(executor.calls) == 1
    assert isinstance(received[0], ActionFeedback)
    assert received[0].outcome is ActionOutcome.LAUNCH_ACCEPTED
    assert isinstance(received[1], ActionNotice)
    assert received[1].reason is ActionNoticeReason.UNSUPPORTED


def test_executor_exception_has_unknown_result_and_next_command_can_run() -> None:
    class FlakyExecutor:
        def __init__(self) -> None:
            self.calls = 0

        def execute(self, request: ActionRequest) -> ActionResult:
            self.calls += 1
            if self.calls == 1:
                raise OSError("private desktop failure")
            return ActionResult(request.key, ActionOutcome.LAUNCH_ACCEPTED)

    action_gate = gate()
    executor = FlakyExecutor()
    first = CommandResolution(
        0,
        CommandIntent(CommandKind.OPEN_APP, "telegram"),
        language="en",
    )
    second = CommandResolution(
        1,
        CommandIntent(CommandKind.OPEN_APP, "telegram"),
        language="en",
    )

    unknown = execute_final_command(first, action_gate, executor)
    accepted = execute_final_command(second, action_gate, executor)

    assert len(unknown) == 1
    assert isinstance(unknown[0], ActionFeedback)
    assert unknown[0].outcome is ActionOutcome.UNKNOWN
    assert unknown[0].error_code == "executor_exception"
    assert len(accepted) == 1
    assert isinstance(accepted[0], ActionFeedback)
    assert accepted[0].outcome is ActionOutcome.LAUNCH_ACCEPTED
