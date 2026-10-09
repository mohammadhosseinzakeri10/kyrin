"""Compound action steps are applied in order with truthful partial results."""

import subprocess
from pathlib import Path

import pytest

from kyrin.actions.gate import ActionGate, ActionPolicy
from kyrin.actions.models import (
    ActionFeedback,
    ActionKey,
    ActionNotice,
    ActionNoticeReason,
    ActionOutcome,
    ActionRequest,
    ActionResult,
)
from kyrin.actions.plan_runner import ActionPlanRunner
from kyrin.actions.platforms.linux import LinuxDesktopEntryExecutor
from kyrin.commands.coordinator import CommandCoordinator
from kyrin.commands.demo_interpreter import DemoCommandInterpreter
from kyrin.commands.models import (
    CommandIntent,
    CommandKind,
    CommandPlan,
    CommandPlanResolution,
    ResponseChannel,
)
from kyrin.responses.presenter import ResponsePresenter
from kyrin.runtime.command_runtime import execute_final_command
from kyrin.stt.transcript import TranscriptStatus, TranscriptUpdate

OPEN_TELEGRAM = CommandIntent(CommandKind.OPEN_APP, "telegram")
OPEN_ALICE_CHAT = CommandIntent(CommandKind.OPEN_CHAT, "alice", "telegram")
PLAN = CommandPlanResolution(
    2, CommandPlan((OPEN_TELEGRAM, OPEN_ALICE_CHAT)), language="en"
)


class FakeExecutor:
    def __init__(self, outcomes: tuple[ActionOutcome, ...]) -> None:
        self.outcomes = outcomes
        self.calls: list[ActionRequest] = []

    def execute(self, request: ActionRequest) -> ActionResult:
        index = len(self.calls)
        self.calls.append(request)
        outcome = self.outcomes[index]
        if outcome is ActionOutcome.CONFIRMED:
            active_app = (
                request.intent.target
                if request.intent.kind is CommandKind.OPEN_APP
                else None
            )
            return ActionResult(request.key, outcome, observed_active_app=active_app)
        if outcome is ActionOutcome.LAUNCH_ACCEPTED:
            return ActionResult(request.key, outcome)
        return ActionResult(request.key, outcome, error_code="test_failure")


def policy(*, chats_supported: bool) -> ActionPolicy:
    return ActionPolicy(
        allowed_apps=frozenset({"telegram"}),
        allowed_chat_apps=frozenset({"telegram"}),
        supported_kinds=frozenset(
            {CommandKind.OPEN_APP, CommandKind.OPEN_CHAT}
            if chats_supported
            else {CommandKind.OPEN_APP}
        ),
    )


def test_executor_exception_stops_plan_with_unknown_outcome() -> None:
    class RaisingExecutor:
        def execute(self, request: ActionRequest) -> ActionResult:
            raise OSError("desktop state is uncertain")

    gate = ActionGate(policy(chats_supported=False))
    runner = ActionPlanRunner(gate, RaisingExecutor())
    result = runner.run(
        CommandPlanResolution(
            0,
            CommandPlan((OPEN_TELEGRAM, OPEN_TELEGRAM)),
            language="en",
        )
    )

    assert len(result) == 1
    assert isinstance(result[0], ActionFeedback)
    assert result[0].outcome is ActionOutcome.UNKNOWN
    assert result[0].error_code == "executor_exception"


def test_first_step_is_executed_then_unsupported_chat_is_explained() -> None:
    gate = ActionGate(policy(chats_supported=False))
    executor = FakeExecutor((ActionOutcome.LAUNCH_ACCEPTED,))
    runner = ActionPlanRunner(gate, executor)

    events = runner.run(PLAN)

    assert [call.key for call in executor.calls] == [ActionKey(0, 2, 0)]
    assert events == (
        ActionFeedback(
            ActionKey(0, 2, 0),
            OPEN_TELEGRAM,
            ActionOutcome.LAUNCH_ACCEPTED,
            channel=ResponseChannel.TEXT_ONLY,
            language="en",
        ),
        ActionNotice(
            ActionKey(0, 2, 1),
            OPEN_ALICE_CHAT,
            ActionNoticeReason.UNSUPPORTED,
            language="en",
        ),
    )
    presenter = ResponsePresenter("en")
    assert "not been confirmed" in presenter.present(events[0]).text
    assert presenter.present(events[1]).text == "I can't open chats yet."
    assert runner.run(PLAN) == ()


def test_failed_first_step_stops_the_plan() -> None:
    executor = FakeExecutor((ActionOutcome.FAILED,))
    events = ActionPlanRunner(ActionGate(policy(chats_supported=False)), executor).run(
        PLAN
    )
    assert len(executor.calls) == 1
    assert len(events) == 1
    assert isinstance(events[0], ActionFeedback)
    assert events[0].outcome is ActionOutcome.FAILED


def test_unverified_launch_cannot_be_followed_by_supported_chat_navigation() -> None:
    executor = FakeExecutor((ActionOutcome.LAUNCH_ACCEPTED,))
    events = ActionPlanRunner(ActionGate(policy(chats_supported=True)), executor).run(
        PLAN
    )
    assert len(executor.calls) == 1
    assert isinstance(events[1], ActionNotice)
    assert events[1].reason is ActionNoticeReason.DEPENDENCY_UNVERIFIED


def test_verified_app_allows_supported_chat_step() -> None:
    executor = FakeExecutor((ActionOutcome.CONFIRMED, ActionOutcome.CONFIRMED))
    events = ActionPlanRunner(
        ActionGate(policy(chats_supported=True)),
        executor,
        observe_active_app=lambda: "telegram",
    ).run(PLAN)
    assert [call.key for call in executor.calls] == [
        ActionKey(0, 2, 0),
        ActionKey(0, 2, 1),
    ]
    assert len(events) == 2
    assert all(isinstance(event, ActionFeedback) for event in events)


def test_runtime_passes_fresh_observation_to_compound_action_runner() -> None:
    executor = FakeExecutor((ActionOutcome.CONFIRMED, ActionOutcome.CONFIRMED))
    observations: list[str] = []

    def observe() -> str:
        observations.append("telegram")
        return "telegram"

    events = execute_final_command(
        PLAN,
        ActionGate(policy(chats_supported=True)),
        executor,
        observe_active_app=observe,
    )

    assert len(events) == 2
    assert len(executor.calls) == 2
    assert observations == ["telegram"]


def test_stale_verified_app_does_not_authorize_chat_after_focus_changes() -> None:
    executor = FakeExecutor((ActionOutcome.CONFIRMED,))
    events = ActionPlanRunner(
        ActionGate(policy(chats_supported=True)),
        executor,
        observe_active_app=lambda: "whatsapp",
    ).run(PLAN)
    assert len(executor.calls) == 1
    assert isinstance(events[1], ActionNotice)
    assert events[1].reason is ActionNoticeReason.DEPENDENCY_UNVERIFIED


def test_independent_open_app_steps_can_continue_after_launch_accepted() -> None:
    plan = CommandPlanResolution(
        3,
        CommandPlan((OPEN_TELEGRAM, CommandIntent(CommandKind.OPEN_APP, "browser"))),
        language="en",
    )
    gate = ActionGate(
        ActionPolicy(
            allowed_apps=frozenset({"telegram", "browser"}),
            supported_kinds=frozenset({CommandKind.OPEN_APP}),
        )
    )
    executor = FakeExecutor(
        (ActionOutcome.LAUNCH_ACCEPTED, ActionOutcome.LAUNCH_ACCEPTED)
    )
    assert len(ActionPlanRunner(gate, executor).run(plan)) == 2
    assert len(executor.calls) == 2


def test_linux_launcher_accepts_first_step_without_attempting_chat(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    entry = tmp_path / "telegram.desktop"
    entry.write_text(
        "[Desktop Entry]\nType=Application\nName=Telegram\nExec=telegram\n"
    )
    launches: list[list[str]] = []

    def fake_run(
        args: list[str], **_kwargs: object
    ) -> subprocess.CompletedProcess[bytes]:
        launches.append(args)
        return subprocess.CompletedProcess(args, 0)

    monkeypatch.setattr(subprocess, "run", fake_run)
    runner = ActionPlanRunner(
        ActionGate(policy(chats_supported=False)),
        LinuxDesktopEntryExecutor({"telegram": entry}),
    )
    decisions = CommandCoordinator(DemoCommandInterpreter()).observe(
        TranscriptUpdate(
            2, "Open Telegram and open Alice chat", TranscriptStatus.FINAL, "en"
        )
    )
    assert len(decisions) == 1
    assert isinstance(decisions[0], CommandPlanResolution)
    events = runner.run(decisions[0])

    assert launches == [["gio", "launch", str(entry)]]
    assert isinstance(events[0], ActionFeedback)
    assert events[0].outcome is ActionOutcome.LAUNCH_ACCEPTED
    assert isinstance(events[1], ActionNotice)
    assert events[1].reason is ActionNoticeReason.UNSUPPORTED
