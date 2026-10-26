"""The application runtime routes repeated speech without a terminal or microphone."""

from collections.abc import Generator
from pathlib import Path
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
from kyrin.actions.queued_dispatch import FinalActionCommand
from kyrin.actions.telegram_selection import TelegramChatSelection
from kyrin.audio.live_speech_pipeline import LiveSpeechEvent
from kyrin.commands.coordinator import CommandCoordinator
from kyrin.commands.demo_interpreter import DemoCommandInterpreter
from kyrin.commands.interpreter import Interpretation, NotACommand
from kyrin.commands.models import (
    CommandContext,
    CommandEvent,
    CommandKind,
    PendingCommandClarification,
)
from kyrin.memory.history import SqliteConversationHistory
from kyrin.runtime.command_runtime import LiveCommandRuntime
from kyrin.runtime.speech_sessions import SpeechSessionEnded
from kyrin.stt.transcript import TranscriptStatus, TranscriptUpdate
from kyrin.system_power.flow import (
    InertPowerBackend,
    PowerAction,
    PowerPrompt,
    PowerStage,
    SystemPowerFlow,
)


class FakeController:
    def __init__(self, events: tuple[LiveSpeechEvent | SpeechSessionEnded, ...]):
        self._events = events
        self.stopped = False

    def events(self) -> Generator[LiveSpeechEvent | SpeechSessionEnded]:
        yield from self._events

    def stop(self) -> None:
        self.stopped = True


def test_power_speech_bypasses_ordinary_command_interpreter() -> None:
    ready = Event()
    requested = Event()
    prompts: list[PowerPrompt] = []
    actions: list[PowerAction] = []
    commands: list[CommandEvent] = []

    class Backend:
        def work_warning(self, action: PowerAction) -> str:
            return "Session blockers unknown."

        def request(self, action: PowerAction) -> None:
            actions.append(action)
            requested.set()

    def publish(prompt: PowerPrompt) -> None:
        prompts.append(prompt)
        if prompt.stage is PowerStage.FIRST:
            ready.set()

    class Controller:
        def events(self) -> Generator[LiveSpeechEvent | SpeechSessionEnded]:
            yield TranscriptUpdate(0, "Power off", TranscriptStatus.PARTIAL, "en")
            assert actions == []
            yield TranscriptUpdate(0, "Power off", TranscriptStatus.FINAL, "en")
            assert ready.wait(2)
            yield TranscriptUpdate(1, "Yes", TranscriptStatus.FINAL, "en")
            yield TranscriptUpdate(2, "Power off", TranscriptStatus.FINAL, "en")
            assert requested.wait(2)

        def stop(self) -> None:
            pass

    runtime = LiveCommandRuntime(
        Controller(),
        coordinator=CommandCoordinator(DemoCommandInterpreter()),
        gate=ActionGate(ActionPolicy()),
        observer=None,
        executor=None,
        on_live_event=lambda event: None,
        on_command_event=commands.append,
        on_action_output=lambda output: None,
        on_session_end=lambda event: None,
        system_power=SystemPowerFlow(Backend(), publish, enabled=True),
    )
    runtime.run()
    assert actions == [PowerAction.POWER_OFF]
    assert commands == []


def test_repeated_finals_across_pause_and_new_stream_keep_listening() -> None:
    first_completed = Event()

    class Controller(FakeController):
        def events(self) -> Generator[LiveSpeechEvent | SpeechSessionEnded]:
            yield TranscriptUpdate(0, "Open Telegram", TranscriptStatus.PARTIAL, "en")
            yield TranscriptUpdate(0, "Open Telegram", TranscriptStatus.FINAL, "en")
            assert first_completed.wait(2)
            yield SpeechSessionEnded(0, None)
            yield TranscriptUpdate(0, "Open browser", TranscriptStatus.FINAL, "en")

    controller = Controller(())
    live: list[LiveSpeechEvent] = []
    commands: list[CommandEvent] = []
    actions: list[ActionDecision | ActionFeedback] = []
    ended: list[SpeechSessionEnded] = []

    def receive(output: ActionDecision | ActionFeedback) -> None:
        actions.append(output)
        first_completed.set()

    runtime = LiveCommandRuntime(
        controller,
        coordinator=CommandCoordinator(DemoCommandInterpreter()),
        gate=ActionGate(
            ActionPolicy(
                allowed_apps=frozenset({"telegram", "browser"}),
                supported_kinds=frozenset({CommandKind.OPEN_APP}),
            )
        ),
        observer=None,
        executor=None,
        on_live_event=live.append,
        on_command_event=commands.append,
        on_action_output=receive,
        on_session_end=ended.append,
    )

    runtime.run()
    runtime.stop()

    assert len(live) == 3
    assert len(ended) == 1
    requests = [action for action in actions if isinstance(action, ActionRequest)]
    assert [action.intent.target for action in requests] == [
        "telegram",
        "browser",
    ]
    assert controller.stopped


def test_final_negation_cannot_execute_partial_positive_command() -> None:
    controller = FakeController(
        (
            TranscriptUpdate(0, "Open Telegram", TranscriptStatus.PARTIAL, "en"),
            TranscriptUpdate(0, "Do not open Telegram", TranscriptStatus.FINAL, "en"),
        )
    )
    actions: list[ActionDecision | ActionFeedback] = []
    runtime = LiveCommandRuntime(
        controller,
        coordinator=CommandCoordinator(DemoCommandInterpreter()),
        gate=ActionGate(
            ActionPolicy(
                allowed_apps=frozenset({"telegram"}),
                supported_kinds=frozenset({CommandKind.OPEN_APP}),
            )
        ),
        observer=None,
        executor=None,
        on_live_event=lambda event: None,
        on_command_event=lambda event: None,
        on_action_output=actions.append,
        on_session_end=lambda event: None,
    )

    runtime.run()

    assert actions == []


def test_only_final_raw_utterances_enter_history_and_context(tmp_path: Path) -> None:
    history = SqliteConversationHistory(tmp_path / "conversation.sqlite3")
    seen_context: list[tuple[str, ...]] = []
    partial_seen = Event()

    class ContextReader:
        def interpret(
            self,
            text: str,
            *,
            language: str | None,
            context: CommandContext,
            pending: PendingCommandClarification | None,
        ) -> Interpretation:
            seen_context.append(context.recent_utterances)
            if not context.is_final_transcript:
                partial_seen.set()
            return NotACommand()

    class Controller(FakeController):
        def events(self) -> Generator[LiveSpeechEvent | SpeechSessionEnded]:
            yield TranscriptUpdate(0, "Open Tele", TranscriptStatus.PARTIAL, "en")
            assert partial_seen.wait(2)
            yield TranscriptUpdate(0, "Open Telegram", TranscriptStatus.FINAL, "en")
            yield TranscriptUpdate(1, "This looks good", TranscriptStatus.FINAL, "en")

    controller = Controller(())
    coordinator = CommandCoordinator(
        ContextReader(),
        recent_utterances=lambda: tuple(turn.text for turn in history.recent(limit=6)),
    )
    runtime = LiveCommandRuntime(
        controller,
        coordinator=coordinator,
        gate=ActionGate(ActionPolicy()),
        observer=None,
        executor=None,
        on_live_event=lambda event: None,
        on_command_event=lambda event: None,
        on_action_output=lambda output: None,
        on_session_end=lambda event: None,
        history=history,
    )
    runtime.run()
    assert seen_context == [(), (), ("Open Telegram",)]
    assert [turn.text for turn in history.recent()] == [
        "Open Telegram",
        "This looks good",
    ]
    history.close()


def test_system_dialogue_discards_an_unfinished_app_fragment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    power = SystemPowerFlow(InertPowerBackend(), lambda _: None, enabled=True)
    monkeypatch.setattr(power, "on_final_speech", lambda text: text == "Power off")

    actions: list[ActionDecision | ActionFeedback] = []
    runtime = LiveCommandRuntime(
        FakeController(
            (
                TranscriptUpdate(0, "Open", TranscriptStatus.FINAL, "en"),
                TranscriptUpdate(1, "Power off", TranscriptStatus.FINAL, "en"),
                TranscriptUpdate(2, "Telegram", TranscriptStatus.FINAL, "en"),
            )
        ),
        coordinator=CommandCoordinator(DemoCommandInterpreter()),
        gate=ActionGate(
            ActionPolicy(
                allowed_apps=frozenset({"telegram"}),
                supported_kinds=frozenset({CommandKind.OPEN_APP}),
            )
        ),
        observer=None,
        executor=None,
        on_live_event=lambda event: None,
        on_command_event=lambda event: None,
        on_action_output=actions.append,
        on_session_end=lambda event: None,
        system_power=power,
    )
    runtime.run()
    assert actions == []


def test_telegram_choice_answer_bypasses_command_interpreter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    answers: list[str] = []
    cancelled = Event()
    choice = TelegramChatSelection(lambda _: None, lambda _: None)

    def choose(text: str) -> bool:
        answers.append(text)
        return text == "own chat"

    monkeypatch.setattr(choice, "on_final_speech", choose)
    monkeypatch.setattr(choice, "cancel", cancelled.set)
    commands: list[CommandEvent] = []
    runtime = LiveCommandRuntime(
        FakeController(
            (TranscriptUpdate(0, "own chat", TranscriptStatus.FINAL, "en"),)
        ),
        coordinator=CommandCoordinator(DemoCommandInterpreter()),
        gate=ActionGate(ActionPolicy()),
        observer=None,
        executor=None,
        on_live_event=lambda _: None,
        on_command_event=commands.append,
        on_action_output=lambda _: None,
        on_session_end=lambda _: None,
        telegram_selection=choice,
    )
    runtime.run()
    assert answers == ["own chat"]
    assert cancelled.is_set()
    assert commands == []


def test_final_executes_on_worker_without_blocking_speech_consumer() -> None:
    completed = Event()
    calls: list[ActionRequest] = []
    outputs: list[ActionDecision | ActionFeedback] = []

    class WaitForActionController:
        def events(self) -> Generator[LiveSpeechEvent | SpeechSessionEnded]:
            yield TranscriptUpdate(0, "Open Telegram", TranscriptStatus.FINAL, "en")
            assert completed.wait(2), "action worker did not finish"

        def stop(self) -> None:
            pass

    class FakeExecutor:
        def execute(self, request: ActionRequest) -> ActionResult:
            calls.append(request)
            return ActionResult(request.key, ActionOutcome.LAUNCH_ACCEPTED)

    def receive(output: ActionDecision | ActionFeedback) -> None:
        outputs.append(output)
        completed.set()

    runtime = LiveCommandRuntime(
        WaitForActionController(),
        coordinator=CommandCoordinator(DemoCommandInterpreter()),
        gate=ActionGate(
            ActionPolicy(
                allowed_apps=frozenset({"telegram"}),
                supported_kinds=frozenset({CommandKind.OPEN_APP}),
            )
        ),
        observer=None,
        executor=FakeExecutor(),
        on_live_event=lambda event: None,
        on_command_event=lambda event: None,
        on_action_output=receive,
        on_session_end=lambda event: None,
    )

    runtime.run()

    assert len(calls) == 1
    assert len(outputs) == 1
    assert isinstance(outputs[0], ActionFeedback)
    assert outputs[0].outcome is ActionOutcome.LAUNCH_ACCEPTED


def test_finite_source_drains_fast_final_commands_without_busy() -> None:
    first_started = Event()
    release_first = Event()
    calls: list[int] = []
    outputs: list[ActionDecision | ActionFeedback] = []
    errors: list[Exception] = []

    class SlowFirstExecutor:
        def execute(self, request: ActionRequest) -> ActionResult:
            if request.key.segment_id == 0:
                first_started.set()
                assert release_first.wait(2)
            calls.append(request.key.segment_id)
            return ActionResult(request.key, ActionOutcome.LAUNCH_ACCEPTED)

    controller = FakeController(
        tuple(
            TranscriptUpdate(index, "Open Telegram", TranscriptStatus.FINAL, "en")
            for index in range(8)
        )
    )
    runtime = LiveCommandRuntime(
        controller,
        coordinator=CommandCoordinator(DemoCommandInterpreter()),
        gate=ActionGate(
            ActionPolicy(
                allowed_apps=frozenset({"telegram"}),
                supported_kinds=frozenset({CommandKind.OPEN_APP}),
            )
        ),
        observer=None,
        executor=SlowFirstExecutor(),
        on_live_event=lambda event: None,
        on_command_event=lambda event: None,
        on_action_output=outputs.append,
        on_session_end=lambda event: None,
        finite_source=True,
    )

    def run() -> None:
        try:
            runtime.run()
        except Exception as exc:
            errors.append(exc)

    runner = Thread(target=run)
    runner.start()
    assert first_started.wait(1)
    release_first.set()
    runner.join(3)

    assert not runner.is_alive()
    assert errors == []
    assert calls == list(range(8))
    assert len(outputs) == 8
    assert all(isinstance(item, ActionFeedback) for item in outputs)


@pytest.mark.parametrize("mode", ("standby", "stop"))
def test_standby_or_stop_invalidates_queued_action_before_stream_ends(
    mode: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first_started = Event()
    second_queued = Event()
    cancelled = Event()
    release_first = Event()
    release_stream = Event()
    calls: list[int] = []
    outputs: list[ActionDecision | ActionFeedback] = []
    errors: list[Exception] = []

    class HoldingController:
        def events(self) -> Generator[LiveSpeechEvent | SpeechSessionEnded]:
            yield TranscriptUpdate(0, "Open Telegram", TranscriptStatus.FINAL, "en")
            yield TranscriptUpdate(1, "Open Telegram", TranscriptStatus.FINAL, "en")
            assert release_stream.wait(2)

        def stop(self) -> None:
            release_stream.set()

    class SlowFirstExecutor:
        def execute(self, request: ActionRequest) -> ActionResult:
            calls.append(request.key.segment_id)
            if request.key.segment_id == 0:
                first_started.set()
                assert release_first.wait(2)
            return ActionResult(request.key, ActionOutcome.LAUNCH_ACCEPTED)

    def receive(output: ActionDecision | ActionFeedback) -> None:
        outputs.append(output)
        if (
            isinstance(output, ActionNotice)
            and output.key.segment_id == 1
            and output.reason is ActionNoticeReason.CANCELLED
        ):
            cancelled.set()

    runtime = LiveCommandRuntime(
        HoldingController(),
        coordinator=CommandCoordinator(DemoCommandInterpreter()),
        gate=ActionGate(
            ActionPolicy(
                allowed_apps=frozenset({"telegram"}),
                supported_kinds=frozenset({CommandKind.OPEN_APP}),
            )
        ),
        observer=None,
        executor=SlowFirstExecutor(),
        on_live_event=lambda event: None,
        on_command_event=lambda event: None,
        on_action_output=receive,
        on_session_end=lambda event: None,
        finite_source=True,
    )

    worker = runtime._worker
    assert worker is not None
    original_submit = worker.submit

    def submit(
        command: FinalActionCommand,
        *,
        wait_for_capacity: bool = False,
        generation: int | None = None,
    ) -> ActionNotice | None:
        notice = original_submit(
            command, wait_for_capacity=wait_for_capacity, generation=generation
        )
        if command.segment_id == 1 and notice is None:
            second_queued.set()
        return notice

    monkeypatch.setattr(worker, "submit", submit)

    def run() -> None:
        try:
            runtime.run()
        except Exception as exc:
            errors.append(exc)

    runner = Thread(target=run)
    runner.start()
    assert first_started.wait(1)
    assert second_queued.wait(1)
    if mode == "standby":
        runtime.set_commands_active(False)
    else:
        runtime.stop()
    assert cancelled.wait(1)
    release_first.set()
    release_stream.set()
    runner.join(3)

    assert not runner.is_alive()
    assert errors == []
    assert calls == [0]


@pytest.mark.parametrize("control", ("Stop listening", "Turn microphone off"))
def test_voice_control_is_consumed_while_understanding_is_blocked(control: str) -> None:
    started = Event()
    release = Event()
    controlled = Event()
    errors: list[Exception] = []
    commands: list[CommandEvent] = []
    actions: list[ActionDecision | ActionFeedback] = []

    class BlockingInterpreter:
        def interpret(
            self,
            text: str,
            *,
            language: str | None,
            context: CommandContext,
            pending: PendingCommandClarification | None,
        ) -> Interpretation:
            started.set()
            assert release.wait(3), "test did not release inference"
            return DemoCommandInterpreter().interpret(
                "Open Telegram", language=language, context=context, pending=pending
            )

    class Source:
        def events(self) -> Generator[LiveSpeechEvent | SpeechSessionEnded]:
            yield TranscriptUpdate(
                0, "slow model request", TranscriptStatus.FINAL, "en"
            )
            assert started.wait(1)
            yield TranscriptUpdate(1, control, TranscriptStatus.FINAL, "en")

        def stop(self) -> None:
            pass

    runtime = LiveCommandRuntime(
        Source(),
        coordinator=CommandCoordinator(BlockingInterpreter()),
        gate=ActionGate(ActionPolicy(allowed_apps=frozenset({"telegram"}))),
        observer=None,
        executor=None,
        on_live_event=lambda _: None,
        on_command_event=commands.append,
        on_action_output=actions.append,
        on_session_end=lambda _: None,
        on_voice_mode=lambda _: controlled.set(),
    )

    def run() -> None:
        try:
            runtime.run()
        except Exception as exc:
            errors.append(exc)

    runner = Thread(target=run)
    runner.start()
    try:
        assert started.wait(1)
        assert controlled.wait(1), "voice control waited behind inference"
        assert commands == []
        assert actions == []
    finally:
        release.set()
        runner.join(3)
    assert not runner.is_alive()
    assert errors == []
    assert commands == []
    assert actions == []
