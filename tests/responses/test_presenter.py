"""User text is localized without changing command or action decisions."""

import pytest

from kyrin.actions.gate import ActionGate, ActionPolicy
from kyrin.actions.models import (
    ActionFeedback,
    ActionKey,
    ActionNotice,
    ActionNoticeReason,
    ActionOutcome,
    ActionResult,
)
from kyrin.audio.audio_backlog import BacklogNotice, BacklogState
from kyrin.audio.audio_errors import AudioError, AudioQueueOverflowError
from kyrin.commands.coordinator import CommandCoordinator
from kyrin.commands.demo_interpreter import DemoCommandInterpreter
from kyrin.commands.models import (
    CommandIntent,
    CommandKind,
    ResponseChannel,
    ResponseKind,
    ResponseRequest,
)
from kyrin.responses.models import SystemNotice, SystemNoticeKind
from kyrin.responses.presenter import PresentedResponse, ResponsePresenter
from kyrin.responses.system_notices import (
    notice_for_backlog,
    notice_for_error,
)
from kyrin.stt.errors import DeviceUnavailableError, SpeechToTextError
from kyrin.stt.transcript import TranscriptStatus, TranscriptUpdate

KEY = ActionKey(2, 7)
TELEGRAM = CommandIntent(CommandKind.OPEN_APP, "telegram")


def test_chat_failure_explains_unsupported_name_and_missing_screen_access() -> None:
    intent = CommandIntent(CommandKind.OPEN_CHAT, "save message", "telegram")
    unsupported = ActionFeedback(
        KEY,
        intent,
        ActionOutcome.FAILED,
        ResponseChannel.TEXT_AND_VOICE,
        "unsupported_chat",
        "en",
    )
    access = ActionFeedback(
        KEY,
        intent,
        ActionOutcome.FAILED,
        ResponseChannel.TEXT_AND_VOICE,
        "screen_access_required",
        "en",
    )
    assert ResponsePresenter("en").present(unsupported).text == (
        "That chat name or app is not supported."
    )
    assert "Screen Access" in ResponsePresenter("en").present(access).text


def test_uncertain_chat_search_shows_the_name_kyrin_actually_searched() -> None:
    intent = CommandIntent(CommandKind.OPEN_CHAT, "call your email", "telegram")
    feedback = ActionFeedback(
        KEY,
        intent,
        ActionOutcome.FAILED,
        ResponseChannel.TEXT_AND_VOICE,
        "chat_search_uncertain",
        "en",
    )
    assert "call your email" in ResponsePresenter("en").present(feedback).text


def test_clarification_is_localized_and_keeps_candidate_order() -> None:
    event = ResponseRequest(
        7,
        ResponseKind.CHOOSE_CHAT_APP,
        ResponseChannel.TEXT_AND_VOICE,
        stream_id=2,
        target="Ali",
        app_candidates=("telegram", "whatsapp"),
    )
    assert ResponsePresenter("fa-IR").present(event) == PresentedResponse(
        2,
        7,
        "چت Ali را در تلگرام باز کنم یا واتساپ؟",
        ResponseChannel.TEXT_AND_VOICE,
        "fa",
    )
    assert ResponsePresenter("en-US").present(event).text == (
        "Should I open Ali's chat in Telegram or WhatsApp?"
    )


def test_unknown_app_context_asks_without_inventing_a_candidate() -> None:
    event = ResponseRequest(
        1, ResponseKind.CHOOSE_CHAT_APP, ResponseChannel.TEXT_AND_VOICE, target="Ali"
    )
    assert ResponsePresenter("en").present(event).text == (
        "Which app should I open the chat in?"
    )


def test_repeat_request_uses_english_fallback_for_unsupported_language() -> None:
    event = ResponseRequest(
        3, ResponseKind.REPEAT_COMMAND, ResponseChannel.TEXT_AND_VOICE
    )
    response = ResponsePresenter("es").present(event)
    assert response.language == "en"
    assert response.text == "I didn't understand. Please repeat the command."


def test_numbered_close_question_is_localized() -> None:
    question = ResponseRequest(
        1, ResponseKind.CONFIRM_NUMBERED_CLOSE, ResponseChannel.TEXT_AND_VOICE,
        target="desktop", window_index=2,
    )
    assert ResponsePresenter("en").present(question).text == (
        "Close window number 2? Yes or no?"
    )
    assert ResponsePresenter("fa").present(question).text == (
        "پنجرهٔ شمارهٔ 2 را ببندم؟ بله یا خیر؟"
    )


def test_conversational_reply_preserves_its_text_and_language() -> None:
    event = ResponseRequest(
        4,
        ResponseKind.CONVERSATION,
        ResponseChannel.TEXT_ONLY,
        language="de",
        message="Hallo!",
    )
    assert ResponsePresenter("en").present(event) == PresentedResponse(
        0, 4, "Hallo!", ResponseChannel.TEXT_ONLY, "de"
    )


def test_event_language_overrides_session_language_with_safe_fallback() -> None:
    presenter = ResponsePresenter("fa")
    english = ResponseRequest(
        1, ResponseKind.REPEAT_COMMAND, ResponseChannel.TEXT_AND_VOICE, language="en-US"
    )
    unsupported = ResponseRequest(
        2, ResponseKind.REPEAT_COMMAND, ResponseChannel.TEXT_AND_VOICE, language="es"
    )
    assert presenter.present(english).language == "en"
    assert presenter.present(english).text.startswith("I didn't")
    assert presenter.present(unsupported).language == "fa"
    assert presenter.present(unsupported).text.startswith("متوجه نشدم")


@pytest.mark.parametrize("reason", list(ActionNoticeReason))
def test_action_notices_have_user_text_and_keep_voice_channel(
    reason: ActionNoticeReason,
) -> None:
    notice = ActionNotice(KEY, TELEGRAM, reason)
    response = ResponsePresenter("fa").present(notice)
    assert response.stream_id == KEY.stream_id
    assert response.segment_id == KEY.segment_id
    assert response.text
    assert reason.value not in response.text
    assert response.channel is ResponseChannel.TEXT_AND_VOICE


def test_accepted_launch_does_not_claim_the_app_opened() -> None:
    feedback = ActionFeedback(
        KEY, TELEGRAM, ActionOutcome.LAUNCH_ACCEPTED, ResponseChannel.TEXT_ONLY
    )
    response = ResponsePresenter("en").present(feedback)
    assert response.text == (
        "The request was accepted; completion has not been confirmed."
    )
    assert response.channel is ResponseChannel.TEXT_ONLY


def test_confirmed_action_has_a_distinct_message() -> None:
    feedback = ActionFeedback(
        KEY, TELEGRAM, ActionOutcome.CONFIRMED, ResponseChannel.TEXT_ONLY
    )
    assert ResponsePresenter("fa").present(feedback).text == "انجام شد."


def test_observed_active_app_has_a_precise_message() -> None:
    feedback = ActionFeedback(
        KEY,
        TELEGRAM,
        ActionOutcome.CONFIRMED,
        ResponseChannel.TEXT_ONLY,
        observed_active_app="telegram",
    )
    assert ResponsePresenter("fa").present(feedback).text == (
        "برنامهٔ موردنظر اکنون فعال است."
    )
    assert ResponsePresenter("en").present(feedback).text == (
        "The requested app is now active."
    )


@pytest.mark.parametrize("outcome", (ActionOutcome.FAILED, ActionOutcome.UNKNOWN))
def test_action_errors_do_not_expose_diagnostic_codes(outcome: ActionOutcome) -> None:
    feedback = ActionFeedback(
        KEY, TELEGRAM, outcome, ResponseChannel.TEXT_AND_VOICE, "secret_os_error"
    )
    response = ResponsePresenter("fa").present(feedback)
    assert response.text
    assert "secret_os_error" not in response.text
    assert response.channel is ResponseChannel.TEXT_AND_VOICE


def test_response_request_rejects_invalid_details() -> None:
    with pytest.raises(ValueError, match="requires a target"):
        ResponseRequest(0, ResponseKind.CHOOSE_CHAT_APP, ResponseChannel.TEXT_ONLY)
    with pytest.raises(ValueError, match="must not have chat details"):
        ResponseRequest(
            0, ResponseKind.REPEAT_COMMAND, ResponseChannel.TEXT_ONLY, target="Ali"
        )


def test_backlog_notices_use_distinct_text_and_voice_channels() -> None:
    presenter = ResponsePresenter("fa")
    waiting = presenter.present(
        notice_for_backlog(BacklogNotice(BacklogState.WAIT, 1000))
    )
    ready = presenter.present(
        notice_for_backlog(BacklogNotice(BacklogState.READY, 200))
    )
    assert waiting.text == "در حال پردازش گفتار قبلی هستم. لطفاً کمی مکث کنید."
    assert waiting.channel is ResponseChannel.TEXT_AND_VOICE
    assert waiting.stream_id is None
    assert ready.channel is ResponseChannel.TEXT_ONLY


def test_failure_notices_hide_raw_exception_text() -> None:
    presenter = ResponsePresenter("en")
    overloaded = presenter.present(
        notice_for_error(AudioQueueOverflowError("private buffer data"))
    )
    transcription = presenter.present(
        notice_for_error(SpeechToTextError("private model path"))
    )
    assert "may have been lost" in overloaded.text
    assert "private buffer data" not in overloaded.text
    assert "private model path" not in transcription.text
    assert overloaded.channel is ResponseChannel.TEXT_AND_VOICE
    assert transcription.channel is ResponseChannel.TEXT_AND_VOICE


def test_missing_model_has_a_specific_safe_message() -> None:
    response = ResponsePresenter("fa").present(
        notice_for_error(FileNotFoundError("/private/model/location"))
    )
    assert response.text == (
        "مدل تشخیص گفتار پیدا نشد. نصب مدل یا مسیر آن را بررسی کنید."
    )
    assert "/private/model/location" not in response.text


@pytest.mark.parametrize(
    ("error", "kind"),
    [
        (AudioError("private device"), SystemNoticeKind.AUDIO_INPUT_FAILURE),
        (
            DeviceUnavailableError("private GPU"),
            SystemNoticeKind.COMPUTE_UNAVAILABLE,
        ),
        (RuntimeError("private state"), SystemNoticeKind.GENERAL_FAILURE),
    ],
)
def test_process_errors_are_classified_without_exposing_details(
    error: Exception, kind: SystemNoticeKind
) -> None:
    notice = notice_for_error(error)
    assert notice.kind is kind
    assert "private" not in ResponsePresenter("en").present(notice).text


def test_system_notice_can_use_an_explicit_event_language() -> None:
    notice = SystemNotice(
        SystemNoticeKind.AUDIO_INPUT_FAILURE,
        ResponseChannel.TEXT_AND_VOICE,
        language="en",
    )
    response = ResponsePresenter("fa").present(notice)
    assert response.language == "en"
    assert response.segment_id is None


def test_listening_retry_notice_is_localized_and_text_only() -> None:
    notice = SystemNotice(SystemNoticeKind.LISTENING_RETRY, ResponseChannel.TEXT_ONLY)
    persian = ResponsePresenter("fa").present(notice)
    english = ResponsePresenter("en").present(notice)
    assert persian.language == "fa"
    assert "دوباره" in persian.text
    assert english.text == "I'm trying to restart speech input."
    assert persian.channel is english.channel is ResponseChannel.TEXT_ONLY


def test_spoken_command_language_reaches_late_action_feedback() -> None:
    coordinator = CommandCoordinator(DemoCommandInterpreter())
    gate = ActionGate(ActionPolicy(allowed_apps=frozenset({"telegram"})))
    events = coordinator.observe(
        TranscriptUpdate(0, "open Telegram", TranscriptStatus.FINAL, "en")
    )
    request = gate.observe(events[0])
    assert request is not None
    feedback = gate.record_result(
        ActionResult(ActionKey(0, 0), ActionOutcome.LAUNCH_ACCEPTED)
    )
    response = ResponsePresenter("fa").present(feedback)
    assert response.language == "en"
    assert response.text == (
        "The request was accepted; completion has not been confirmed."
    )
