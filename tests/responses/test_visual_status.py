"""Visual feedback follows evidence from command and action events."""

import pytest

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
from kyrin.runtime.speech_sessions import SpeechSessionEnded
from kyrin.runtime.voice_control import VoiceMode, VoiceModeChanged
from kyrin.stt.transcript import TranscriptStatus, TranscriptUpdate


def activity(transition: SpeechTransition) -> SpeechActivityFrame:
    return SpeechActivityFrame(
        AudioData(b"", AudioFormat(16000, 1, AudioSampleFormat.INT16)),
        transition is SpeechTransition.STARTED,
        SpeechState.SPEAKING
        if transition is SpeechTransition.STARTED
        else SpeechState.LISTENING,
        transition,
    )


def test_partial_speech_stays_listening_then_transcribing_then_understanding() -> None:
    states: list[VisualPresentation] = []
    visual = VisualStatusController(states.append)
    visual.on_live_event(activity(SpeechTransition.STARTED))
    visual.on_live_event(TranscriptUpdate(0, "open", TranscriptStatus.PARTIAL))
    assert states[-1].status is VisualStatus.LISTENING
    visual.on_live_event(activity(SpeechTransition.PAUSED))
    assert states[-1].caption == "Transcribing speech…"
    visual.on_live_event(TranscriptUpdate(0, "open Telegram", TranscriptStatus.FINAL))
    assert states[-1].caption == "Understanding request…"


def test_new_utterance_protects_caption_before_its_first_transcript() -> None:
    states: list[VisualPresentation] = []
    visual = VisualStatusController(states.append)
    visual.on_live_event(TranscriptUpdate(0, "previous speech", TranscriptStatus.FINAL))
    visual.on_live_event(activity(SpeechTransition.STARTED))
    expected = states[-1]
    visual.on_command_event(
        ResponseRequest(
            0,
            ResponseKind.CONVERSATION,
            ResponseChannel.TEXT_ONLY,
            message="Delayed old response",
        )
    )
    assert states[-1] == expected
    assert latest_status(states) is VisualStatus.LISTENING


@pytest.mark.parametrize(
    "kind",
    [
        ResponseKind.CONVERSATION,
        ResponseKind.READY_FOR_COMMAND,
        ResponseKind.REPEAT_COMMAND,
    ],
)
def test_late_speech_pause_cannot_erase_a_completed_response(
    kind: ResponseKind,
) -> None:
    states: list[VisualPresentation] = []
    visual = VisualStatusController(states.append)
    visual.on_live_event(activity(SpeechTransition.STARTED))
    visual.on_live_event(TranscriptUpdate(0, "hello", TranscriptStatus.FINAL))
    visual.on_command_event(
        ResponseRequest(
            0,
            kind,
            ResponseChannel.TEXT_ONLY,
            message="Actual model reply" if kind is ResponseKind.CONVERSATION else None,
        )
    )
    expected = states[-1]
    visual.on_live_event(activity(SpeechTransition.PAUSED))
    assert states[-1] == expected
    visual.on_live_event(activity(SpeechTransition.STARTED))
    visual.on_live_event(activity(SpeechTransition.PAUSED))
    assert states[-1].caption == "Transcribing speech…"  # A genuinely new utterance.


@pytest.mark.parametrize("status", [TranscriptStatus.PARTIAL, TranscriptStatus.FINAL])
def test_sealed_transcript_cannot_reopen_processing_after_a_reply(
    status: TranscriptStatus,
) -> None:
    states: list[VisualPresentation] = []
    visual = VisualStatusController(states.append)
    visual.on_live_event(TranscriptUpdate(0, "hello", TranscriptStatus.FINAL))
    visual.on_command_event(
        ResponseRequest(
            0, ResponseKind.CONVERSATION, ResponseChannel.TEXT_ONLY, message="Reply"
        )
    )
    expected = states[-1]
    visual.on_live_event(TranscriptUpdate(0, "hello", status))
    assert states[-1] == expected


def test_inference_after_streaming_final_does_not_wait_for_vad_pause() -> None:
    from kyrin.timing import TimingEvent

    states: list[VisualPresentation] = []
    visual = VisualStatusController(states.append)
    visual.on_live_event(activity(SpeechTransition.STARTED))
    visual.on_live_event(TranscriptUpdate(0, "hello", TranscriptStatus.FINAL))
    visual.on_timing(TimingEvent("s", ActionKey(0, 0), "inference_started", 1))
    assert states[-1].caption == "The model is processing your request…"


@pytest.mark.parametrize("mode", [VoiceMode.ACTIVE, VoiceMode.STANDBY])
def test_diagnostic_playback_error_keeps_action_state_and_ignores_late_errors(
    mode: VoiceMode,
) -> None:
    states: list[VisualPresentation] = []
    visual = VisualStatusController(states.append, voice_mode=mode)
    visual.on_action_start(
        ActionRequest(
            ActionKey(0, 0), CommandIntent(CommandKind.MINIMIZE_APP, "telegram")
        )
    )
    visual.on_playback_error()
    assert states[-1].status is VisualStatus.EXECUTING
    assert states[-1].caption.startswith("Minimizing telegram…")
    assert "Voice output failed" in states[-1].caption
    visual.on_playback_error()
    assert states[-1].caption.count("Voice output failed") == 1
    assert states[-1].caption.count("Standby.") == (mode is VoiceMode.STANDBY)
    visual.on_closed()
    expected = states[-1]
    visual.on_playback_error()
    assert states[-1] == expected


def test_standby_ignores_transcripts_and_late_replies_without_inventing_mode() -> None:
    states: list[VisualPresentation] = []
    visual = VisualStatusController(states.append)
    visual.on_voice_state(
        VoiceModeChanged(VoiceMode.STANDBY, session_id="a", revision=2)
    )
    expected = states[-1]
    visual.on_live_event(TranscriptUpdate(0, "private words", TranscriptStatus.FINAL))
    visual.on_command_event(
        ResponseRequest(
            0,
            ResponseKind.CONVERSATION,
            ResponseChannel.TEXT_ONLY,
            message="old reply",
        )
    )
    visual.on_voice_state(
        VoiceModeChanged(VoiceMode.ACTIVE, session_id="a", revision=1)
    )
    assert states[-1] == expected
    assert "Start listening" in expected.caption
    visual.on_voice_state(
        VoiceModeChanged(VoiceMode.ACTIVE, session_id="a", revision=3)
    )
    # Recognizing a control for rendering does not itself change routing mode.
    visual.on_live_event(TranscriptUpdate(1, "stop listening", TranscriptStatus.FINAL))
    assert states[-1].caption == "Ready to listen…"


def test_capture_retry_failure_and_shutdown_cannot_claim_ready_early() -> None:
    states: list[VisualPresentation] = []
    visual = VisualStatusController(states.append, capture_ready=False)
    assert states[-1].caption == "Starting microphone…"
    visual.on_capture_ready()
    assert states[-1].caption == "Ready to listen…"
    visual.on_session_end(SpeechSessionEnded(0, RuntimeError("private error"), 1))
    assert "reconnecting" in states[-1].caption
    visual.on_live_event(TranscriptUpdate(0, "old", TranscriptStatus.FINAL))
    assert "reconnecting" in states[-1].caption
    visual.on_capture_ready()
    assert states[-1].caption == "Ready to listen…"
    visual.on_stopping()
    expected = states[-1]
    visual.on_capture_ready()
    assert states[-1] == expected
    visual.on_closed()
    assert "Microphone off" in states[-1].caption
    expected = states[-1]
    visual.on_live_event(activity(SpeechTransition.STARTED))
    visual.on_capture_ready()
    assert states[-1] == expected


def test_terminal_listening_error_is_retained_when_context_closes() -> None:
    states: list[VisualPresentation] = []
    visual = VisualStatusController(states.append)
    visual.on_session_end(SpeechSessionEnded(0, RuntimeError("private error")))
    assert states[-1].status is VisualStatus.FAILED
    assert "private error" not in states[-1].caption
    visual.on_capture_ready()
    visual.on_closed()
    assert states[-1].status is VisualStatus.FAILED


def test_action_result_retains_evidence_and_adds_standby_guidance() -> None:
    states: list[VisualPresentation] = []
    visual = VisualStatusController(states.append)
    request = ActionRequest(
        ActionKey(0, 0), CommandIntent(CommandKind.OPEN_APP, "telegram")
    )
    visual.on_action_start(request)
    visual.on_voice_state(VoiceModeChanged(VoiceMode.STANDBY))
    assert latest_status(states) is VisualStatus.EXECUTING
    visual.on_action_output(
        ActionFeedback(
            request.key,
            request.intent,
            ActionOutcome.CONFIRMED,
            ResponseChannel.TEXT_ONLY,
        )
    )
    assert latest_status(states) is VisualStatus.CONFIRMED
    assert "Start listening" in states[-1].caption


def test_cancelled_selection_still_explains_standby_after_stop_listening() -> None:
    states: list[VisualPresentation] = []
    visual = VisualStatusController(states.append)
    request = ActionRequest(
        ActionKey(0, 0), CommandIntent(CommandKind.OPEN_CHAT, "Ada", "telegram")
    )
    visual.on_action_start(request)
    visual.on_chat_selection_prompt(
        ResponseRequest(
            0, ResponseKind.CHOOSE_CHAT_APP, ResponseChannel.TEXT_ONLY, target="Ada"
        )
    )
    visual.on_voice_state(VoiceModeChanged(VoiceMode.STANDBY))
    visual.on_action_output(
        ActionFeedback(
            request.key,
            request.intent,
            ActionOutcome.FAILED,
            ResponseChannel.TEXT_ONLY,
            "chat_selection_cancelled",
        )
    )
    assert "cancelled" in states[-1].caption
    assert "Standby. Say Start listening" in states[-1].caption


def test_action_result_keeps_a_concurrent_capture_failure_visible() -> None:
    states: list[VisualPresentation] = []
    visual = VisualStatusController(states.append)
    request = ActionRequest(
        ActionKey(0, 0), CommandIntent(CommandKind.MINIMIZE_APP, "telegram")
    )
    visual.on_action_start(request)
    visual.on_session_end(SpeechSessionEnded(0, RuntimeError("private failure"), 1))
    visual.on_action_output(
        ActionFeedback(
            request.key,
            request.intent,
            ActionOutcome.CONFIRMED,
            ResponseChannel.TEXT_ONLY,
        )
    )
    assert states[-1].status is VisualStatus.CONFIRMED
    assert "Done." in states[-1].caption
    assert "reconnecting" in states[-1].caption
    assert "private failure" not in states[-1].caption


def test_closed_file_after_standby_does_not_invite_speech_to_closed_capture() -> None:
    states: list[VisualPresentation] = []
    visual = VisualStatusController(states.append, file_input=True)
    visual.on_voice_state(VoiceModeChanged(VoiceMode.STANDBY))
    visual.on_action_start(
        ActionRequest(ActionKey(0, 0), CommandIntent(CommandKind.OPEN_APP, "telegram"))
    )
    visual.on_action_output(
        ActionFeedback(
            ActionKey(0, 0),
            CommandIntent(CommandKind.OPEN_APP, "telegram"),
            ActionOutcome.CONFIRMED,
            ResponseChannel.TEXT_ONLY,
        )
    )
    visual.on_playback_error()
    visual.on_closed()
    assert "Audio file processing finished" in states[-1].caption
    assert "Say Start listening" not in states[-1].caption


def test_empty_transcript_ends_processing_without_hiding_a_persisted_result() -> None:
    states: list[VisualPresentation] = []
    visual = VisualStatusController(states.append)
    visual.on_live_event(activity(SpeechTransition.STARTED))
    visual.on_live_event(activity(SpeechTransition.PAUSED))
    visual.on_live_event(TranscriptUpdate(0, "", TranscriptStatus.FINAL))
    assert states[-1].status is VisualStatus.READY
    visual.on_action_error()
    expected = states[-1]
    visual.on_live_event(TranscriptUpdate(1, "", TranscriptStatus.FINAL))
    assert states[-1] == expected


def test_file_cancellation_does_not_claim_finished_or_microphone_readiness() -> None:
    states: list[VisualPresentation] = []
    visual = VisualStatusController(states.append, file_input=True)
    assert states[-1].caption == "Processing audio file…"
    visual.on_stopping()
    visual.on_closed()
    assert states[-1].caption == "Audio file processing stopped."


def test_persian_standby_ready_transcription_and_off_captions() -> None:
    states: list[VisualPresentation] = []
    visual = VisualStatusController(
        states.append, language="fa", voice_mode=VoiceMode.STANDBY
    )
    assert "آماده‌باش" in states[-1].caption
    assert "Start listening" in states[-1].caption
    visual.on_voice_state(VoiceModeChanged(VoiceMode.ACTIVE))
    assert states[-1].caption == "آمادهٔ شنیدن…"
    visual.on_live_event(activity(SpeechTransition.PAUSED))
    assert states[-1].caption == "در حال تبدیل گفتار به متن…"
    visual.on_closed()
    assert "میکروفن خاموش" in states[-1].caption


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


def test_chat_choice_prompt_replaces_running_action_and_can_finish() -> None:
    states: list[VisualPresentation] = []
    controller = VisualStatusController(states.append)
    intent = CommandIntent(CommandKind.OPEN_CHAT, "My Mother", "telegram")
    request = ActionRequest(ActionKey(0, 1), intent, "en")
    controller.on_action_start(request)
    prompt = ResponseRequest(
        1,
        ResponseKind.CONVERSATION,
        ResponseChannel.TEXT_AND_VOICE,
        stream_id=0,
        language="en",
        message="Which chat? Say 1 or 2.",
    )
    controller.on_chat_selection_prompt(prompt)
    assert states[-1] == VisualPresentation(
        VisualStatus.QUESTION, "Which chat? Say 1 or 2."
    )
    controller.on_action_output(
        ActionFeedback(
            request.key,
            intent,
            ActionOutcome.FAILED,
            ResponseChannel.TEXT_AND_VOICE,
            "chat_selection_expired",
            "en",
        )
    )
    assert latest_status(states) is VisualStatus.QUESTION


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
    assert states[2].caption == "Opening or bringing telegram forward…"


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
    assert states[-1].caption == "Opening a new window of terminal…"


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
    assert updates[-1].caption == "در حال بازکردن یا جلوآوردن telegram…"


def test_same_status_with_new_action_caption_is_published() -> None:
    updates: list[VisualPresentation] = []
    controller = VisualStatusController(updates.append)
    controller.on_action_start(
        ActionRequest(ActionKey(0, 1), CommandIntent(CommandKind.OPEN_APP, "telegram"))
    )
    controller.on_action_start(
        ActionRequest(ActionKey(0, 2), CommandIntent(CommandKind.OPEN_APP, "browser"))
    )
    assert updates[-2].caption == "Opening or bringing telegram forward…"
    assert updates[-1].caption == "Opening or bringing browser forward…"
