"""User-facing caption contracts across every supported command and result kind."""

from dataclasses import replace

import pytest

from kyrin.actions.control_policy import (
    ControlCapability,
    ControlConfirmation,
    ControlEvidence,
)
from kyrin.actions.models import (
    ActionFeedback,
    ActionKey,
    ActionNotice,
    ActionNoticeReason,
    ActionOutcome,
    ActionRequest,
)
from kyrin.audio.audio_backlog import BacklogNotice, BacklogState
from kyrin.audio.audio_errors import AudioError, AudioQueueOverflowError
from kyrin.commands.models import (
    CommandIntent,
    CommandKind,
    CommandPlan,
    CommandPlanResolution,
    CommandResolution,
    ResponseChannel,
    ResponseKind,
    ResponseRequest,
)
from kyrin.desktop.window_observation import WindowObservation
from kyrin.responses.presenter import ResponsePresenter
from kyrin.responses.system_notices import notice_for_error
from kyrin.responses.visual_captions import action_caption
from kyrin.responses.visual_router import VisualPresentationRouter
from kyrin.responses.visual_status import (
    VisualPresentation,
    VisualStatus,
    VisualStatusController,
    power_presentation,
)
from kyrin.runtime.speech_sessions import SpeechSessionEnded
from kyrin.runtime.voice_control import VoiceMode, VoiceModeChanged
from kyrin.stt.errors import DeviceUnavailableError, SpeechToTextError
from kyrin.stt.transcript import TranscriptStatus, TranscriptUpdate
from kyrin.system_power.flow import PowerAction, PowerPrompt, PowerStage
from kyrin.timing import TimingEvent


def latest_status(presentations: list[VisualPresentation]) -> VisualStatus:
    return presentations[-1].status


def intent(kind: CommandKind) -> CommandIntent:
    if kind is CommandKind.OPEN_CHAT:
        return CommandIntent(kind, "Ada", "telegram")
    if kind is CommandKind.TELEGRAM_VIEW:
        return CommandIntent(kind, "archive")
    if kind is CommandKind.TELEGRAM_SETTINGS:
        return CommandIntent(kind, "privacy")
    if kind in {CommandKind.SELECT_APP_WINDOW, CommandKind.CLOSE_SHOWN_WINDOW}:
        return CommandIntent(kind, "terminal", window_index=2)
    return CommandIntent(kind, "telegram")


@pytest.mark.parametrize("kind", list(CommandKind))
@pytest.mark.parametrize("language", ["en", "fa"])
def test_all_operations_have_explicit_progress_instead_of_generic_working(
    kind: CommandKind,
    language: str,
) -> None:
    presentations: list[VisualPresentation] = []
    visual = VisualStatusController(presentations.append, language=language)
    visual.on_action_start(ActionRequest(ActionKey(0, 0), intent(kind)))
    caption = presentations[-1].caption
    assert presentations[-1].status is VisualStatus.EXECUTING
    assert "Working with" not in caption
    assert "در حال انجام فرمان روی" not in caption
    assert "{" not in caption
    assert len(caption) > 10
    if kind in {CommandKind.SELECT_APP_WINDOW, CommandKind.CLOSE_SHOWN_WINDOW}:
        assert "2" in caption
    if kind is CommandKind.MINIMIZE_APP and language == "en":
        assert caption == "Minimizing telegram…"
    if kind is CommandKind.NEW_APP_TAB and language == "en":
        assert caption == "Opening a new tab in telegram…"
    if kind is CommandKind.TELEGRAM_VIEW and language == "en":
        assert "archive" in caption


@pytest.mark.parametrize("kind", list(CommandKind))
@pytest.mark.parametrize("outcome", list(ActionOutcome))
def test_all_result_outcomes_keep_operation_context_and_success_evidence(
    kind: CommandKind,
    outcome: ActionOutcome,
) -> None:
    presentations: list[VisualPresentation] = []
    visual = VisualStatusController(presentations.append)
    request = ActionRequest(ActionKey(0, 0), intent(kind))
    visual.on_action_start(request)
    visual.on_action_output(
        ActionFeedback(
            request.key,
            request.intent,
            outcome,
            ResponseChannel.TEXT_ONLY,
            error_code="private_backend_detail"
            if outcome in {ActionOutcome.FAILED, ActionOutcome.UNKNOWN}
            else None,
        )
    )
    expected = {
        ActionOutcome.CONFIRMED: VisualStatus.CONFIRMED,
        ActionOutcome.LAUNCH_ACCEPTED: VisualStatus.UNVERIFIED,
        ActionOutcome.DISPATCHED_UNVERIFIED: VisualStatus.UNVERIFIED,
        ActionOutcome.UNKNOWN: VisualStatus.UNVERIFIED,
        ActionOutcome.FAILED: VisualStatus.FAILED,
    }[outcome]
    if (
        kind in {CommandKind.SHOW_ALL_WINDOWS, CommandKind.SHOW_APP_WINDOWS}
        and outcome is ActionOutcome.LAUNCH_ACCEPTED
    ):
        expected = VisualStatus.QUESTION
        assert "window number" in presentations[-1].caption
    else:
        assert action_caption(request.intent, "en") in presentations[-1].caption
    assert presentations[-1].status is expected
    assert "private_backend_detail" not in presentations[-1].caption
    assert "Start listening" not in presentations[-1].caption


@pytest.mark.parametrize("reason", list(ActionNoticeReason))
def test_policy_notices_have_the_correct_scenario_and_do_not_claim_execution(
    reason: ActionNoticeReason,
) -> None:
    presentations: list[VisualPresentation] = []
    visual = VisualStatusController(presentations.append)
    visual.on_action_output(
        ActionNotice(ActionKey(0, 0), intent(CommandKind.MINIMIZE_APP), reason)
    )
    assert (
        presentations[-1].status
        is {
            ActionNoticeReason.NOT_ALLOWED: VisualStatus.FAILED,
            ActionNoticeReason.CONFIRMATION_REQUIRED: VisualStatus.QUESTION,
            ActionNoticeReason.BUSY: VisualStatus.READY,
            ActionNoticeReason.CANCELLED: VisualStatus.READY,
            ActionNoticeReason.UNSUPPORTED: VisualStatus.FAILED,
            ActionNoticeReason.DEPENDENCY_UNVERIFIED: VisualStatus.UNVERIFIED,
        }[reason]
    )
    assert presentations[-1].caption.startswith("Minimize telegram — ")


def response(kind: ResponseKind) -> ResponseRequest:
    base = ResponseRequest(
        0, ResponseKind.READY_FOR_COMMAND, ResponseChannel.TEXT_ONLY, language="fa"
    )
    if kind is ResponseKind.CONVERSATION:
        return replace(base, kind=kind, message="پاسخ خود مدل حفظ می‌شود.")
    if kind in {
        ResponseKind.CHOOSE_CHAT_APP,
        ResponseKind.CONFIRM_APP,
        ResponseKind.CHOOSE_APP_OR_CHAT,
    }:
        return replace(base, kind=kind, target="Ada")
    if kind is ResponseKind.CHOOSE_APP:
        return replace(base, kind=kind, app_candidates=("Telegram", "Terminal"))
    if kind is ResponseKind.CHOOSE_OPERATION:
        return replace(
            base,
            kind=kind,
            target="terminal",
            operation_candidates=(CommandKind.OPEN_APP, CommandKind.MINIMIZE_APP),
        )
    if kind is ResponseKind.CONFIRM_ACTION:
        return replace(
            base,
            kind=kind,
            target="terminal",
            operation_candidates=(CommandKind.CLOSE_APP_WINDOW,),
        )
    if kind is ResponseKind.CONFIRM_NUMBERED_CLOSE:
        return replace(base, kind=kind, target="terminal", window_index=2)
    if kind is ResponseKind.CHOOSE_WINDOW:
        return replace(base, kind=kind, target="terminal", window_count=2)
    return replace(base, kind=kind)


@pytest.mark.parametrize("kind", list(ResponseKind))
def test_every_reply_and_clarification_has_english_chrome_with_original_model_text(
    kind: ResponseKind,
) -> None:
    presentations: list[VisualPresentation] = []
    visual = VisualStatusController(presentations.append)
    event = response(kind)
    visual.on_command_event(event)
    if kind is ResponseKind.CONVERSATION:
        assert presentations[-1] == VisualPresentation(
            VisualStatus.CONVERSATION, event.message or ""
        )
    else:
        assert presentations[-1].status is (
            VisualStatus.READY
            if kind is ResponseKind.READY_FOR_COMMAND
            else VisualStatus.QUESTION
        )
        assert all(
            ord(character) < 0x600 or ord(character) > 0x6FF
            for character in presentations[-1].caption
        )


def test_caption_language_is_independent_of_transcript_and_action_language() -> None:
    presentations: list[VisualPresentation] = []
    visual = VisualStatusController(presentations.append)
    visual.on_live_event(TranscriptUpdate(0, "باز کن", TranscriptStatus.FINAL, "fa"))
    assert presentations[-1].caption == "Understanding request…"
    request = ActionRequest(
        ActionKey(0, 0), intent(CommandKind.MINIMIZE_APP), language="fa"
    )
    visual.on_action_start(request)
    assert presentations[-1].caption == "Minimizing telegram…"
    visual.on_action_output(
        ActionFeedback(
            request.key,
            request.intent,
            ActionOutcome.CONFIRMED,
            ResponseChannel.TEXT_ONLY,
            language="fa",
        )
    )
    assert presentations[-1].caption == "Minimize telegram — Done."
    visual.on_closed()
    assert "Microphone off" in presentations[-1].caption


def test_queue_and_model_stages_do_not_claim_execution_or_erase_a_reply() -> None:
    presentations: list[VisualPresentation] = []
    visual = VisualStatusController(presentations.append)
    visual.on_live_event(
        TranscriptUpdate(0, "minimize terminal", TranscriptStatus.FINAL)
    )
    for stage, phrase in (
        ("understanding_queued", "queued"),
        ("model_resource_wait_started", "Waiting for"),
        ("inference_started", "model is processing"),
    ):
        visual.on_timing(TimingEvent("s", ActionKey(0, 0), stage, 1))
        assert phrase in presentations[-1].caption
        assert presentations[-1].status is VisualStatus.PROCESSING
    visual.on_command_event(CommandResolution(0, intent(CommandKind.MINIMIZE_APP)))
    assert "Checking permission" in presentations[-1].caption
    visual.on_timing(TimingEvent("s", ActionKey(0, 0), "action_queued", 2))
    assert presentations[-1].caption == "Queued for execution: Minimize telegram…"
    assert presentations[-1].status is VisualStatus.PROCESSING
    visual.on_command_event(response(ResponseKind.CONVERSATION))
    expected = presentations[-1]
    visual.on_timing(TimingEvent("s", ActionKey(0, 0), "inference_finished", 3))
    assert presentations[-1] == expected


def test_plan_caption_distinguishes_queue_from_each_real_step() -> None:
    presentations: list[VisualPresentation] = []
    visual = VisualStatusController(presentations.append)
    plan = CommandPlan((intent(CommandKind.OPEN_APP), intent(CommandKind.MINIMIZE_APP)))
    visual.on_command_event(CommandPlanResolution(0, plan))
    assert presentations[-1].caption == "Checking permission: 2-step command plan…"
    visual.on_timing(TimingEvent("s", ActionKey(0, 0), "action_queued", 1))
    assert presentations[-1].caption == "Queued for execution: 2-step command plan…"
    assert latest_status(presentations) is VisualStatus.PROCESSING
    for index, step in enumerate(plan.steps):
        request = ActionRequest(ActionKey(0, 0, index), step)
        visual.on_action_start(request)
        assert presentations[-1].caption == action_caption(step, "en", running=True)
        assert latest_status(presentations) is VisualStatus.EXECUTING
        visual.on_action_output(
            ActionFeedback(
                request.key, step, ActionOutcome.CONFIRMED, ResponseChannel.TEXT_ONLY
            )
        )
    expected = presentations[-1]
    visual.on_action_output(
        ActionFeedback(
            ActionKey(0, 0),
            plan.steps[0],
            ActionOutcome.CONFIRMED,
            ResponseChannel.TEXT_ONLY,
        )
    )
    assert presentations[-1] == expected  # A late first-step result stays stale.


def test_control_consent_is_a_question_until_the_existing_dialog_approves() -> None:
    presentations: list[VisualPresentation] = []
    visual = VisualStatusController(presentations.append)
    request = ActionRequest(
        ActionKey(0, 0), CommandIntent(CommandKind.VISIBLE_CONTROL, "Mode")
    )
    visual.on_action_start(request)
    prompt = ControlConfirmation(
        request.key,
        ControlCapability.ACTIVATE,
        ControlEvidence("Mode", "ocr", None, None, (10, 20)),
        WindowObservation("app.desktop", 42, "window-7", "initial", 1, 10),
        None,
        "fa",
    )
    visual.on_control_prompt(prompt)
    assert presentations[-1] == VisualPresentation(
        VisualStatus.QUESTION, "Confirm in the dialog: Activate control Mode"
    )
    visual.on_control_approved()
    assert latest_status(presentations) is VisualStatus.EXECUTING
    visual.on_action_output(
        ActionFeedback(
            request.key,
            request.intent,
            ActionOutcome.UNKNOWN,
            ResponseChannel.TEXT_ONLY,
            "unknown",
        )
    )
    assert latest_status(presentations) is VisualStatus.UNVERIFIED
    visual.on_voice_state(VoiceModeChanged(VoiceMode.STANDBY, session_id="s"))
    expected = presentations[-1]
    visual.on_control_prompt(prompt)
    visual.on_control_approved()
    visual.on_chat_selection_prompt(response(ResponseKind.CHOOSE_WINDOW))
    assert presentations[-1] == expected


def test_backlog_recovery_does_not_erase_a_new_reply() -> None:
    presentations: list[VisualPresentation] = []
    visual = VisualStatusController(presentations.append)
    visual.on_live_event(BacklogNotice(BacklogState.WAIT, 1000))
    assert "earlier speech" in presentations[-1].caption
    visual.on_command_event(response(ResponseKind.CONVERSATION))
    expected = presentations[-1]
    visual.on_live_event(BacklogNotice(BacklogState.READY, 100))
    assert presentations[-1] == expected


def test_stale_reply_and_result_cannot_replace_newer_speech_or_action() -> None:
    presentations: list[VisualPresentation] = []
    visual = VisualStatusController(presentations.append)
    visual.on_live_event(
        TranscriptUpdate(2, "new request", TranscriptStatus.FINAL), stream_id=1
    )
    expected = presentations[-1]
    visual.on_command_event(response(ResponseKind.CONVERSATION))
    assert presentations[-1] == expected
    current = ActionRequest(ActionKey(1, 2), intent(CommandKind.MINIMIZE_APP))
    visual.on_action_start(current)
    expected = presentations[-1]
    visual.on_action_output(
        ActionFeedback(
            ActionKey(0, 0),
            intent(CommandKind.OPEN_APP),
            ActionOutcome.CONFIRMED,
            ResponseChannel.TEXT_ONLY,
        )
    )
    assert presentations[-1] == expected


def test_dry_run_and_file_completion_preserve_the_real_outcome() -> None:
    presentations: list[VisualPresentation] = []
    visual = VisualStatusController(presentations.append, file_input=True)
    request = ActionRequest(ActionKey(0, 0), intent(CommandKind.MINIMIZE_APP))
    visual.on_action_output(request)
    assert "no action was executed" in presentations[-1].caption
    assert presentations[-1].status == VisualStatus.READY
    visual.on_action_start(request)
    visual.on_action_output(
        ActionFeedback(
            request.key,
            request.intent,
            ActionOutcome.UNKNOWN,
            ResponseChannel.TEXT_ONLY,
            "unknown",
        )
    )
    expected = presentations[-1].caption
    visual.on_closed()
    assert latest_status(presentations) is VisualStatus.UNVERIFIED
    assert presentations[-1].caption.startswith(expected)
    assert "Audio file processing finished" in presentations[-1].caption


@pytest.mark.parametrize("stage", list(PowerStage))
@pytest.mark.parametrize("preview", [False, True])
@pytest.mark.parametrize("action", list(PowerAction))
def test_every_power_stage_distinguishes_consent_preview_and_accepted_request(
    stage: PowerStage,
    preview: bool,
    action: PowerAction,
) -> None:
    prompt = PowerPrompt(1, action, stage, "Specific power scenario", preview=preview)
    presentation = power_presentation(prompt)
    assert presentation.caption == prompt.text
    assert presentation.status is not VisualStatus.CONFIRMED
    if stage in {PowerStage.FIRST, PowerStage.SECOND}:
        assert presentation.status is VisualStatus.QUESTION
    if preview:
        assert presentation.status is not VisualStatus.EXECUTING
    elif stage is PowerStage.FINISHED:
        assert presentation.status is VisualStatus.UNVERIFIED


def test_system_confirmation_priority_and_stale_power_prompts() -> None:
    presentations: list[VisualPresentation] = []
    router = VisualPresentationRouter(presentations.append)
    prompt = PowerPrompt(2, PowerAction.RESTART, PowerStage.SECOND, "Confirm restart")
    router.publish_power(prompt)
    router.publish(VisualPresentation(VisualStatus.READY, "Ready to listen…"))
    router.publish_power(
        replace(prompt, request_id=1, stage=PowerStage.FIRST, text="old prompt")
    )
    assert presentations[-1].caption == "Confirm restart"
    router.publish_power(
        replace(prompt, stage=PowerStage.CANCELLED, text="Restart cancelled")
    )
    assert presentations[-1].caption == "Restart cancelled"
    router.publish(VisualPresentation(VisualStatus.READY, "Ready to listen…"))
    assert presentations[-1].caption == "Ready to listen…"


def test_model_failure_is_not_misreported_as_misunderstood_speech() -> None:
    presentations: list[VisualPresentation] = []
    visual = VisualStatusController(presentations.append)
    visual.on_live_event(TranscriptUpdate(0, "Hello", TranscriptStatus.FINAL))
    visual.on_timing(TimingEvent("s", ActionKey(0, 0), "inference_started", 1))
    visual.on_timing(TimingEvent("s", ActionKey(0, 0), "model_failed", 2))
    visual.on_command_event(CommandResolution(0, None))
    visual.on_command_event(response(ResponseKind.REPEAT_COMMAND))
    assert latest_status(presentations) is VisualStatus.FAILED
    assert "request model failed" in presentations[-1].caption
    assert "didn't understand" not in presentations[-1].caption


def test_repeated_control_reasserts_mode_after_independent_power_caption() -> None:
    presentations: list[VisualPresentation] = []
    router = VisualPresentationRouter(presentations.append)
    visual = VisualStatusController(router.publish)
    state = VoiceModeChanged(VoiceMode.ACTIVE, session_id="s")
    prompt = PowerPrompt(1, PowerAction.RESTART, PowerStage.FIRST, "Confirm restart")
    router.publish_power(prompt)
    visual.on_voice_state(state)
    assert presentations[-1].caption == "Confirm restart"
    router.publish_power(
        replace(prompt, stage=PowerStage.CANCELLED, text="Restart cancelled")
    )
    visual.on_voice_state(state)  # A repeated Start listening is acknowledged.
    assert presentations[-1].caption == "Ready to listen…"


def test_old_selection_timeout_cannot_erase_a_new_conversation_reply() -> None:
    presentations: list[VisualPresentation] = []
    visual = VisualStatusController(presentations.append)
    request = ActionRequest(ActionKey(0, 0), intent(CommandKind.OPEN_CHAT))
    visual.on_action_start(request)
    visual.on_chat_selection_prompt(response(ResponseKind.CHOOSE_APP))
    visual.on_live_event(TranscriptUpdate(1, "new topic", TranscriptStatus.FINAL))
    visual.on_command_event(replace(response(ResponseKind.CONVERSATION), segment_id=1))
    expected = presentations[-1]
    visual.on_action_output(
        ActionFeedback(
            request.key,
            request.intent,
            ActionOutcome.FAILED,
            ResponseChannel.TEXT_ONLY,
            "chat_selection_expired",
        )
    )
    assert presentations[-1] == expected
    visual.on_chat_selection_prompt(response(ResponseKind.CHOOSE_APP))
    assert presentations[-1] == expected


def test_auxiliary_notice_keeps_the_primary_scenario_and_clears_on_next_event() -> None:
    presentations: list[VisualPresentation] = []
    router = VisualPresentationRouter(presentations.append)
    progress = VisualPresentation(VisualStatus.EXECUTING, "Minimizing telegram…")
    router.publish(progress)
    notice = VisualPresentation(VisualStatus.FAILED, "Voice output failed.")
    router.publish_notice(notice)
    assert presentations[-1].status is VisualStatus.EXECUTING
    assert presentations[-1].caption == "Minimizing telegram… Voice output failed."
    router.publish_notice(notice)
    assert presentations[-1].caption.count("Voice output failed.") == 1
    finished = VisualPresentation(VisualStatus.CONFIRMED, "Minimize telegram — Done.")
    router.publish(finished)
    assert presentations[-1] == finished


@pytest.mark.parametrize(
    "error",
    [
        AudioError("private error"),
        SpeechToTextError("private error"),
        DeviceUnavailableError("private error"),
        FileNotFoundError("private error"),
        RuntimeError("private error"),
        AudioQueueOverflowError(
            "private error", buffer="capture_queue", pending=2, limit=1, unit="chunks"
        ),
    ],
)
@pytest.mark.parametrize("retry", [False, True])
def test_specific_audio_errors_and_retry_have_relevant_english_text(
    error: Exception,
    retry: bool,
) -> None:
    presentations: list[VisualPresentation] = []
    visual = VisualStatusController(presentations.append)
    visual.on_session_end(SpeechSessionEnded(0, error, 1 if retry else None))
    expected = ResponsePresenter("en").present(notice_for_error(error)).text
    assert expected in presentations[-1].caption
    assert "private error" not in presentations[-1].caption
    assert (
        "reconnecting" in presentations[-1].caption
        if retry
        else latest_status(presentations) is VisualStatus.FAILED
    )
