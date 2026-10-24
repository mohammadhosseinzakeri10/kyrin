"""Session cancellation must reach an already running compound command."""

from collections.abc import Generator
from threading import Event, Thread

import pytest

from kyrin.actions.gate import ActionGate, ActionPolicy
from kyrin.actions.models import (
    ActionDecision,
    ActionFeedback,
    ActionNotice,
    ActionNoticeReason,
    ActionOutcome,
    ActionRequest,
    ActionResult,
)
from kyrin.commands.coordinator import CommandCoordinator
from kyrin.commands.demo_interpreter import DemoCommandInterpreter
from kyrin.runtime.command_runtime import LiveCommandRuntime
from kyrin.runtime.speech_sessions import SpeechRuntimeEvent, SpeechSessionEnded
from kyrin.stt.transcript import TranscriptStatus, TranscriptUpdate


@pytest.mark.parametrize("mode", ("stop", "pause", "pause_resume", "stream", "eof"))
def test_session_cancellation_reaches_active_plan_without_rolling_back_first_step(
    mode: str,
) -> None:
    started = Event()
    release = Event()
    finish_stream = Event()
    stream_ended = Event()
    delivered = Event()
    calls: list[int] = []
    outputs: list[ActionDecision | ActionFeedback] = []
    errors: list[Exception] = []

    class Source:
        def events(self) -> Generator[SpeechRuntimeEvent]:
            yield TranscriptUpdate(
                0, "Open Telegram and open browser", TranscriptStatus.FINAL, "en"
            )
            assert finish_stream.wait(3)
            yield SpeechSessionEnded(1, None, None)

        def stop(self) -> None:
            finish_stream.set()

    class Executor:
        def execute(self, request: ActionRequest) -> ActionResult:
            calls.append(request.key.step_index)
            if request.key.step_index == 0:
                started.set()
                assert release.wait(3)
            return ActionResult(request.key, ActionOutcome.LAUNCH_ACCEPTED)

    def receive(output: ActionDecision | ActionFeedback) -> None:
        outputs.append(output)
        if len(outputs) == 2:
            delivered.set()

    runtime = LiveCommandRuntime(
        Source(),
        coordinator=CommandCoordinator(DemoCommandInterpreter()),
        gate=ActionGate(ActionPolicy(allowed_apps=frozenset({"telegram", "browser"}))),
        observer=None,
        executor=Executor(),
        on_live_event=lambda _: None,
        on_command_event=lambda _: None,
        on_action_output=receive,
        on_session_end=lambda _: stream_ended.set(),
        finite_source=mode != "stream",
    )

    def run() -> None:
        try:
            runtime.run()
        except Exception as exc:
            errors.append(exc)

    runner = Thread(target=run)
    runner.start()
    try:
        assert started.wait(2)
        if mode == "stop":
            runtime.stop()
        elif mode in ("pause", "pause_resume"):
            runtime.set_commands_active(False)
            if mode == "pause_resume":
                runtime.set_commands_active(True)
        finish_stream.set()
        if mode != "stop":
            assert stream_ended.wait(2)
        release.set()
        assert delivered.wait(2)
    finally:
        release.set()
        finish_stream.set()
        runner.join(4)
    assert not runner.is_alive()
    assert errors == []
    assert calls == ([0, 1] if mode == "eof" else [0])
    assert len(outputs) == 2
    first, second = outputs
    assert isinstance(first, ActionFeedback)
    assert first.outcome is ActionOutcome.LAUNCH_ACCEPTED
    assert first.key.step_index == 0
    assert second.key.step_index == 1
    if mode == "eof":
        assert isinstance(second, ActionFeedback)
        assert second.outcome is ActionOutcome.LAUNCH_ACCEPTED
    else:
        assert isinstance(second, ActionNotice)
        assert second.reason is ActionNoticeReason.CANCELLED


@pytest.mark.parametrize("compound", (False, True))
def test_cancellation_after_gate_before_dispatch_releases_unsent_request(
    compound: bool,
) -> None:
    from kyrin.actions.cancellation import ActionExecutionContext
    from kyrin.commands.models import (
        CommandEvent,
        CommandIntent,
        CommandKind,
        CommandPlan,
        CommandPlanResolution,
        CommandResolution,
    )
    from kyrin.runtime.command_runtime import execute_final_command

    entered = Event()
    release = Event()
    context = ActionExecutionContext(7)
    intent = CommandIntent(CommandKind.OPEN_APP, "telegram")
    calls: list[ActionRequest] = []
    outputs: list[ActionNotice | ActionFeedback] = []

    class HoldingGate(ActionGate):
        def observe(self, event: CommandEvent) -> ActionDecision | None:
            result = super().observe(event)
            if isinstance(result, ActionRequest) and result.key.segment_id == 0:
                entered.set()
                assert release.wait(3)
            return result

    class Executor:
        def execute(self, request: ActionRequest) -> ActionResult:
            calls.append(request)
            return ActionResult(request.key, ActionOutcome.LAUNCH_ACCEPTED)

    gate = HoldingGate(
        ActionPolicy(allowed_apps=frozenset({"telegram"}), max_pending=1)
    )
    command = (
        CommandPlanResolution(0, CommandPlan((intent, intent)), language="fa")
        if compound
        else CommandResolution(0, intent, language="fa")
    )

    def run() -> None:
        outputs.extend(
            execute_final_command(command, gate, Executor(), context=context)
        )

    runner = Thread(target=run)
    runner.start()
    try:
        assert entered.wait(2)
        context.cancel()
    finally:
        release.set()
        runner.join(3)
    assert not runner.is_alive()
    assert calls == []
    assert len(outputs) == 1
    assert isinstance(outputs[0], ActionNotice)
    assert outputs[0].reason is ActionNoticeReason.CANCELLED
    assert outputs[0].language == "fa"
    # Cancellation frees capacity, keeps duplicate suppression, and creates no fact.
    assert gate.observe(CommandResolution(0, intent)) is None
    assert gate.verified_context.active_app is None
    assert isinstance(gate.observe(CommandResolution(1, intent)), ActionRequest)
