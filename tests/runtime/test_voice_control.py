"""Voice standby ignores ordinary speech and only exact controls change mode."""

from kyrin.actions.gate import ActionGate, ActionPolicy
from kyrin.actions.models import ActionDecision, ActionFeedback, ActionRequest
from kyrin.audio.live_speech_pipeline import LiveSpeechEvent
from kyrin.commands.coordinator import CommandCoordinator
from kyrin.commands.demo_interpreter import DemoCommandInterpreter
from kyrin.commands.models import CommandEvent, CommandKind
from kyrin.runtime.command_runtime import LiveCommandRuntime
from kyrin.runtime.voice_control import VoiceMode, VoiceModeChanged, control_phrase
from kyrin.stt.transcript import TranscriptStatus, TranscriptUpdate


def test_control_phrases_are_exact_and_case_insensitive() -> None:
    assert control_phrase("Start Listening!", active=False) is VoiceMode.ACTIVE
    assert control_phrase("Stop listening.", active=True) is VoiceMode.STANDBY
    assert control_phrase(
        "Turn off the microphone completely.", active=True
    ) is VoiceMode.OFF
    assert control_phrase("Turn microphone off.", active=True) is VoiceMode.OFF
    assert control_phrase("Turn microphone off.", active=False) is VoiceMode.OFF
    assert control_phrase("میکروفن را کامل خاموش کن", active=False) is VoiceMode.OFF
    assert control_phrase("please start listening", active=False) is None
    assert control_phrase("start listening and open Telegram", active=False) is None


def test_standby_filters_speech_and_full_off_request() -> None:
    transcript = tuple(
        TranscriptUpdate(index, text, TranscriptStatus.FINAL, "en")
        for index, text in enumerate(
            (
                "Open Telegram",
                "Start listening",
                "Open Telegram",
                "Stop listening",
                "Open browser",
                "Start listening",
                "Turn off microphone completely",
                "Open browser",
            )
        )
    )

    class Source:
        def events(self):
            yield from transcript

        def stop(self) -> None:
            pass

    live: list[LiveSpeechEvent] = []
    commands: list[CommandEvent] = []
    actions: list[ActionDecision | ActionFeedback] = []
    modes: list[VoiceModeChanged] = []
    runtime = LiveCommandRuntime(
        Source(),
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
        on_session_end=lambda _event: None,
        voice_standby=True,
        on_voice_mode=modes.append,
    )
    runtime.run()
    assert [event.mode for event in modes] == [
        VoiceMode.ACTIVE, VoiceMode.STANDBY, VoiceMode.ACTIVE, VoiceMode.OFF
    ]
    assert [event.text for event in live if isinstance(event, TranscriptUpdate)] == [
        "Start listening", "Open Telegram", "Stop listening",
        "Start listening", "Turn off microphone completely",
    ]
    assert [
        action.intent.target
        for action in actions
        if isinstance(action, ActionRequest)
    ] == ["telegram"]


def test_standby_can_turn_microphone_off_without_resuming_commands() -> None:
    transcript = (
        TranscriptUpdate(0, "Start listening", TranscriptStatus.FINAL, "en"),
        TranscriptUpdate(1, "Stop listening", TranscriptStatus.FINAL, "en"),
        TranscriptUpdate(2, "Turn microphone off", TranscriptStatus.FINAL, "en"),
    )

    class Source:
        def events(self):
            yield from transcript

        def stop(self) -> None:
            pass

    modes: list[VoiceModeChanged] = []
    runtime = LiveCommandRuntime(
        Source(),
        coordinator=None,
        gate=None,
        observer=None,
        executor=None,
        on_live_event=lambda _event: None,
        on_command_event=lambda _event: None,
        on_action_output=lambda _event: None,
        on_session_end=lambda _event: None,
        voice_standby=True,
        on_voice_mode=modes.append,
    )

    runtime.run()

    assert [event.mode for event in modes] == [
        VoiceMode.ACTIVE,
        VoiceMode.STANDBY,
        VoiceMode.OFF,
    ]
