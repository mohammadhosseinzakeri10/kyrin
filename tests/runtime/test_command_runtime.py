"""The application runtime routes repeated speech without a terminal or microphone."""

from collections.abc import Generator
from threading import Event

from kyrin.actions.gate import ActionGate, ActionPolicy
from kyrin.actions.models import (
    ActionDecision,
    ActionFeedback,
    ActionOutcome,
    ActionRequest,
    ActionResult,
)
from kyrin.audio.live_speech_pipeline import LiveSpeechEvent
from kyrin.commands.coordinator import CommandCoordinator
from kyrin.commands.demo_interpreter import DemoCommandInterpreter
from kyrin.commands.interpreter import NotACommand
from kyrin.commands.models import CommandEvent, CommandKind
from kyrin.memory.history import SqliteConversationHistory
from kyrin.runtime.command_runtime import LiveCommandRuntime
from kyrin.runtime.speech_sessions import SpeechSessionEnded
from kyrin.stt.transcript import TranscriptStatus, TranscriptUpdate
from kyrin.system_power.flow import (
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
            yield TranscriptUpdate(
                2, "Power off", TranscriptStatus.FINAL, "en"
            )
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
    controller = FakeController(
        (
            TranscriptUpdate(0, "Open Telegram", TranscriptStatus.PARTIAL, "en"),
            TranscriptUpdate(0, "Open Telegram", TranscriptStatus.FINAL, "en"),
            SpeechSessionEnded(0, None),
            TranscriptUpdate(0, "Open browser", TranscriptStatus.FINAL, "en"),
        )
    )
    live: list[LiveSpeechEvent] = []
    commands: list[CommandEvent] = []
    actions: list[ActionDecision | ActionFeedback] = []
    ended: list[SpeechSessionEnded] = []
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
        on_action_output=actions.append,
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


def test_only_final_raw_utterances_enter_history_and_context(tmp_path) -> None:
    history = SqliteConversationHistory(tmp_path / "conversation.sqlite3")
    seen_context: list[tuple[str, ...]] = []

    class ContextReader:
        def interpret(self, text, *, language, context, pending):
            seen_context.append(context.recent_utterances)
            return NotACommand()

    controller = FakeController(
        (
            TranscriptUpdate(0, "Open Tele", TranscriptStatus.PARTIAL, "en"),
            TranscriptUpdate(0, "Open Telegram", TranscriptStatus.FINAL, "en"),
            TranscriptUpdate(1, "This looks good", TranscriptStatus.FINAL, "en"),
        )
    )
    coordinator = CommandCoordinator(
        ContextReader(),
        recent_utterances=lambda: tuple(
            turn.text for turn in history.recent(limit=6)
        ),
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
        "Open Telegram", "This looks good"
    ]
    history.close()


def test_system_dialogue_discards_an_unfinished_app_fragment() -> None:
    class FakePowerFlow:
        def on_final_speech(self, text: str) -> bool:
            return text == "Power off"

        def cancel(self) -> None:
            pass

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
        system_power=FakePowerFlow(),
    )
    runtime.run()
    assert actions == []


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
