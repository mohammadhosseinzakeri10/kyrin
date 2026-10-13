"""Visual feedback follows evidence from command and action events."""

from kyrin.actions.models import (
    ActionFeedback,
    ActionKey,
    ActionNotice,
    ActionNoticeReason,
    ActionOutcome,
    ActionRequest,
)
from kyrin.audio.activity.speech_activity_monitor import (
    SpeechActivityFrame,
    SpeechState,
    SpeechTransition,
)
from kyrin.audio.audio_data import AudioData
from kyrin.audio.audio_format import AudioFormat, AudioSampleFormat
from kyrin.commands.models import (
    CommandIntent,
    CommandKind,
    CommandResolution,
    ResponseChannel,
    ResponseKind,
    ResponseRequest,
)
from kyrin.responses.visual_status import (
    VisualPresentation,
    VisualStatus,
    VisualStatusController,
)
from kyrin.stt.transcript import TranscriptStatus, TranscriptUpdate


def latest_status(states: list[VisualPresentation]) -> VisualStatus:
    return states[-1].status


def test_waiting_and_speaking_have_different_visual_states() -> None:
    states: list[VisualPresentation] = []
    controller = VisualStatusController(states.append)
    assert latest_status(states) is VisualStatus.READY

    controller.on_live_event(
        SpeechActivityFrame(
            AudioData(b"", AudioFormat(16000, 1, AudioSampleFormat.INT16)),
            True,
            SpeechState.SPEAKING,
            SpeechTransition.STARTED,
        )
    )
    assert latest_status(states) is VisualStatus.LISTENING


def test_final_non_command_returns_to_ready_before_an_optional_question() -> None:
    states: list[VisualPresentation] = []
    controller = VisualStatusController(states.append, language="fa")
    controller.on_live_event(TranscriptUpdate(0, "سلام", TranscriptStatus.FINAL, "fa"))
    controller.on_command_event(CommandResolution(0, None, language="fa"))
    assert latest_status(states) is VisualStatus.READY
    assert states[-1].caption == "آمادهٔ شنیدن…"

    controller.on_live_event(
        TranscriptUpdate(1, "باز کن", TranscriptStatus.FINAL, "fa")
    )
    controller.on_command_event(CommandResolution(1, None, language="fa"))
    controller.on_command_event(
        ResponseRequest(
            1,
            ResponseKind.REPEAT_COMMAND,
            ResponseChannel.TEXT_AND_VOICE,
            language="fa",
        )
    )
    assert latest_status(states) is VisualStatus.QUESTION


def test_wake_only_shows_readiness_without_a_question_state() -> None:
    states: list[VisualPresentation] = []
    controller = VisualStatusController(states.append)
    controller.on_command_event(
        ResponseRequest(
            0, ResponseKind.READY_FOR_COMMAND, ResponseChannel.TEXT_ONLY, language="en"
        )
    )
    assert states[-1] == VisualPresentation(
        VisualStatus.READY, "I'm listening. Tell me what to do."
    )


def test_conversation_shows_reply_without_an_action_success_state() -> None:
    states: list[VisualPresentation] = []
    controller = VisualStatusController(states.append)
    controller.on_command_event(
        ResponseRequest(
            0,
            ResponseKind.CONVERSATION,
            ResponseChannel.TEXT_ONLY,
            language="en",
            message="Hello! I'm KYRIN. How can I help?",
        )
    )
    assert states[-1] == VisualPresentation(
        VisualStatus.CONVERSATION, "Hello! I'm KYRIN. How can I help?"
    )


def test_non_command_does_not_hide_an_action_still_running() -> None:
    states: list[VisualPresentation] = []
    controller = VisualStatusController(states.append)
    controller.on_action_start(
        ActionRequest(ActionKey(0, 0), CommandIntent(CommandKind.OPEN_APP, "telegram"))
    )
    controller.on_command_event(CommandResolution(1, None, language="en"))
    assert latest_status(states) is VisualStatus.EXECUTING


def test_execution_status_requires_actual_start_and_evidence_for_success() -> None:
    states: list[VisualPresentation] = []
    controller = VisualStatusController(states.append)
    intent = CommandIntent(CommandKind.OPEN_APP, "telegram")
    key = ActionKey(0, 1)
    request = ActionRequest(key, intent)

    controller.on_live_event(
        TranscriptUpdate(1, "Open Telegram", TranscriptStatus.FINAL)
    )
    controller.on_action_start(request)
    controller.on_live_event(
        TranscriptUpdate(2, "Open browser", TranscriptStatus.PARTIAL)
    )
    controller.on_action_output(
        ActionFeedback(
            key, intent, ActionOutcome.LAUNCH_ACCEPTED, ResponseChannel.TEXT_AND_VOICE
        )
    )
    assert [state.status for state in states] == [
        VisualStatus.READY,
        VisualStatus.PROCESSING,
        VisualStatus.EXECUTING,
        VisualStatus.UNVERIFIED,
    ]

    controller.on_action_start(request)
    controller.on_action_output(
        ActionFeedback(
            key, intent, ActionOutcome.CONFIRMED, ResponseChannel.TEXT_AND_VOICE
        )
    )
    assert states[-1].status is VisualStatus.CONFIRMED
    assert states[2].caption == "Opening telegram…"


def test_terminal_picker_keeps_the_mascot_in_question_state() -> None:
    states: list[VisualPresentation] = []
    controller = VisualStatusController(states.append)
    intent = CommandIntent(CommandKind.SHOW_APP_WINDOWS, "terminal")
    request = ActionRequest(ActionKey(0, 0), intent, "en")
    controller.on_action_start(request)
    controller.on_action_output(
        ActionFeedback(
            request.key,
            intent,
            ActionOutcome.LAUNCH_ACCEPTED,
            ResponseChannel.TEXT_ONLY,
            language="en",
        )
    )
    assert states[-1].status is VisualStatus.QUESTION
    assert "window number" in states[-1].caption


def test_window_action_does_not_claim_to_open_a_chat() -> None:
    states: list[VisualPresentation] = []
    controller = VisualStatusController(states.append)
    controller.on_action_start(
        ActionRequest(
            ActionKey(0, 0),
            CommandIntent(CommandKind.NEW_APP_WINDOW, "terminal"),
        )
    )
    assert states[-1].caption == "Working with terminal…"


def test_clarification_and_blocked_action_have_distinct_statuses() -> None:
    states: list[VisualPresentation] = []
    controller = VisualStatusController(states.append)
    controller.on_command_event(
        ResponseRequest(1, ResponseKind.REPEAT_COMMAND, ResponseChannel.TEXT_AND_VOICE)
    )
    assert latest_status(states) is VisualStatus.QUESTION
    assert states[-1].caption == "I didn't understand. Please repeat the command."

    intent = CommandIntent(CommandKind.OPEN_APP, "telegram")
    controller.on_action_output(
        ActionNotice(ActionKey(0, 1), intent, ActionNoticeReason.NOT_ALLOWED)
    )
    assert latest_status(states) is VisualStatus.FAILED
    assert VisualStatus.EXECUTING not in [state.status for state in states]


def test_busy_notice_does_not_end_another_running_action() -> None:
    states: list[VisualPresentation] = []
    controller = VisualStatusController(states.append)
    intent = CommandIntent(CommandKind.OPEN_APP, "telegram")
    key = ActionKey(0, 1)
    controller.on_action_start(ActionRequest(key, intent))
    controller.on_action_output(
        ActionNotice(ActionKey(0, 2), intent, ActionNoticeReason.BUSY)
    )
    assert latest_status(states) is VisualStatus.EXECUTING
    controller.on_action_output(
        ActionFeedback(
            key, intent, ActionOutcome.CONFIRMED, ResponseChannel.TEXT_AND_VOICE
        )
    )
    assert latest_status(states) is VisualStatus.CONFIRMED


def test_dry_run_request_never_claims_an_action_was_launched() -> None:
    states: list[VisualPresentation] = []
    controller = VisualStatusController(states.append)
    controller.on_live_event(
        TranscriptUpdate(1, "Open Telegram", TranscriptStatus.FINAL)
    )
    intent = CommandIntent(CommandKind.OPEN_APP, "telegram")
    controller.on_action_output(ActionRequest(ActionKey(0, 1), intent))
    assert [state.status for state in states] == [
        VisualStatus.READY,
        VisualStatus.PROCESSING,
        VisualStatus.READY,
    ]


def test_visual_caption_uses_requested_language_and_action_target() -> None:
    updates: list[VisualPresentation] = []
    controller = VisualStatusController(updates.append, language="fa")
    intent = CommandIntent(CommandKind.OPEN_APP, "telegram")
    controller.on_action_start(ActionRequest(ActionKey(0, 1), intent, language="fa"))
    assert updates[0].caption == "آمادهٔ شنیدن…"
    assert updates[-1].caption == "در حال بازکردن telegram…"


def test_same_status_with_new_action_caption_is_published() -> None:
    updates: list[VisualPresentation] = []
    controller = VisualStatusController(updates.append)
    controller.on_action_start(
        ActionRequest(ActionKey(0, 1), CommandIntent(CommandKind.OPEN_APP, "telegram"))
    )
    controller.on_action_start(
        ActionRequest(ActionKey(0, 2), CommandIntent(CommandKind.OPEN_APP, "browser"))
    )
    assert updates[-2].caption == "Opening telegram…"
    assert updates[-1].caption == "Opening browser…"
