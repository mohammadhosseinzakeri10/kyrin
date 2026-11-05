"""English V1 behavior keeps presentation, speech and target text separate."""

import re
from dataclasses import replace

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
from kyrin.commands.coordinator import CommandCoordinator
from kyrin.commands.demo_interpreter import DemoCommandInterpreter
from kyrin.commands.models import (
    CommandIntent,
    CommandKind,
    CommandResolution,
    ResponseChannel,
    ResponseKind,
    ResponseRequest,
)
from kyrin.responses.models import SystemNotice, SystemNoticeKind
from kyrin.responses.presenter import ResponsePresenter
from kyrin.responses.speech import ResponseSpeaker
from kyrin.responses.visual_status import (
    VisualPresentation,
    VisualStatus,
    VisualStatusController,
)
from kyrin.runtime.command_runtime import dispatch_command_action
from kyrin.stt.transcript import TranscriptStatus, TranscriptUpdate


@pytest.mark.parametrize(
    "kind", [CommandKind.SHOW_ALL_WINDOWS, CommandKind.SHOW_APP_WINDOWS]
)
@pytest.mark.parametrize("event_language", ["en", "fa", None])
@pytest.mark.parametrize(
    ("visual_language", "caption"),
    [
        ("en-US", "Say a window number or click its preview."),
        ("fa-IR", "شمارهٔ پنجره را بگویید یا روی آن کلیک کنید."),
    ],
)
def test_window_choice_keeps_visual_language_independent_of_command(
    kind: CommandKind,
    event_language: str | None,
    visual_language: str,
    caption: str,
) -> None:
    updates: list[VisualPresentation] = []
    visual = VisualStatusController(updates.append, language=visual_language)
    request = ActionRequest(
        ActionKey(0, 0), CommandIntent(kind, "telegram"), language=event_language
    )
    visual.on_action_start(request)
    visual.on_action_output(
        ActionFeedback(
            request.key,
            request.intent,
            ActionOutcome.LAUNCH_ACCEPTED,
            ResponseChannel.TEXT_ONLY,
            language=event_language,
        )
    )

    assert updates[-1].status is VisualStatus.QUESTION
    assert updates[-1].caption == caption


@pytest.mark.parametrize("kind", list(SystemNoticeKind))
@pytest.mark.parametrize("event_language", [None, "en-US", "de-DE"])
def test_system_notices_have_english_fallback_without_raw_identifiers(
    kind: SystemNoticeKind, event_language: str | None
) -> None:
    notice = SystemNotice(kind, ResponseChannel.TEXT_AND_VOICE, event_language)
    response = ResponsePresenter("en").present(notice)

    assert response.language == "en"
    assert not re.search(r"[\u0600-\u06ff]", response.text)
    assert response.text and kind.value not in response.text
    assert response.channel is notice.channel


@pytest.mark.parametrize("reason", list(ActionNoticeReason))
def test_english_policy_messages_override_persian_session_fallback(
    reason: ActionNoticeReason,
) -> None:
    notice = ActionNotice(
        ActionKey(0, 0),
        CommandIntent(CommandKind.OPEN_APP, "telegram"),
        reason,
        language="en-GB",
    )
    response = ResponsePresenter("fa").present(notice)

    assert response.language == "en"
    assert not re.search(r"[\u0600-\u06ff]", response.text)
    assert response.text
    assert response.channel is notice.channel


@pytest.mark.parametrize("kind", list(ResponseKind))
def test_every_question_has_english_text_and_preserves_response_channel(
    kind: ResponseKind,
) -> None:
    details: dict[ResponseKind, ResponseRequest] = {
        ResponseKind.CHOOSE_CHAT_APP: ResponseRequest(
            0,
            ResponseKind.CHOOSE_CHAT_APP,
            ResponseChannel.TEXT_ONLY,
            target="Ali",
            app_candidates=("telegram", "whatsapp"),
        ),
        ResponseKind.CHOOSE_APP: ResponseRequest(
            0,
            ResponseKind.CHOOSE_APP,
            ResponseChannel.TEXT_ONLY,
            app_candidates=("Calculator", "Calendar"),
        ),
        ResponseKind.CONFIRM_APP: ResponseRequest(
            0,
            ResponseKind.CONFIRM_APP,
            ResponseChannel.TEXT_ONLY,
            target="telegram",
        ),
        ResponseKind.CHOOSE_APP_OR_CHAT: ResponseRequest(
            0,
            ResponseKind.CHOOSE_APP_OR_CHAT,
            ResponseChannel.TEXT_ONLY,
            target="telegram",
        ),
        ResponseKind.CHOOSE_OPERATION: ResponseRequest(
            0,
            ResponseKind.CHOOSE_OPERATION,
            ResponseChannel.TEXT_ONLY,
            target="Terminal",
            operation_candidates=(CommandKind.OPEN_APP, CommandKind.NEW_APP_WINDOW),
        ),
        ResponseKind.CHOOSE_WINDOW: ResponseRequest(
            0,
            ResponseKind.CHOOSE_WINDOW,
            ResponseChannel.TEXT_ONLY,
            target="Terminal",
            window_count=2,
        ),
        ResponseKind.CONFIRM_ACTION: ResponseRequest(
            0,
            ResponseKind.CONFIRM_ACTION,
            ResponseChannel.TEXT_ONLY,
            target="Terminal",
            operation_candidates=(CommandKind.MINIMIZE_APP,),
        ),
        ResponseKind.CONFIRM_NUMBERED_CLOSE: ResponseRequest(
            0,
            ResponseKind.CONFIRM_NUMBERED_CLOSE,
            ResponseChannel.TEXT_ONLY,
            target="Terminal",
            window_index=2,
        ),
        ResponseKind.CONVERSATION: ResponseRequest(
            0,
            ResponseKind.CONVERSATION,
            ResponseChannel.TEXT_ONLY,
            message="Hello!",
        ),
    }
    event = details.get(kind) or ResponseRequest(0, kind, ResponseChannel.TEXT_ONLY)
    event = replace(event, language="en")
    response = ResponsePresenter("fa").present(event)

    assert response.language == "en"
    assert not re.search(r"[\u0600-\u06ff]", response.text)
    assert response.text and kind.value not in response.text
    assert response.channel is ResponseChannel.TEXT_ONLY


@pytest.mark.parametrize("outcome", list(ActionOutcome))
def test_english_chat_clarification_preserves_persian_target_through_voice(
    outcome: ActionOutcome,
) -> None:
    """Start at the transcript boundary; never open a model or desktop adapter."""
    target = "علی رضایی"
    coordinator = CommandCoordinator(DemoCommandInterpreter())
    presenter = ResponsePresenter("fa")
    gate = ActionGate(ActionPolicy(allowed_chat_apps=frozenset({"telegram"})))
    requests: list[ActionRequest] = []
    spoken: list[tuple[str, str]] = []

    class Executor:
        def execute(self, request: ActionRequest) -> ActionResult:
            requests.append(request)
            return ActionResult(
                request.key,
                outcome,
                error_code="chat_search_uncertain"
                if outcome in {ActionOutcome.FAILED, ActionOutcome.UNKNOWN}
                else None,
            )

    class Voice:
        def speak(self, text: str, language: str) -> None:
            spoken.append((text, language))

    partial = coordinator.observe(
        TranscriptUpdate(0, f"Open chat {target}", TranscriptStatus.PARTIAL, "en")
    )
    assert all(
        not dispatch_command_action(event, gate, Executor()) for event in partial
    )
    events = coordinator.observe(
        TranscriptUpdate(0, f"Open chat {target}", TranscriptStatus.FINAL, "en")
    )
    question = next(event for event in events if isinstance(event, ResponseRequest))
    rendered = presenter.present(question)
    assert question.target == target
    assert rendered.language == "en"
    assert not re.search(r"[\u0600-\u06ff]", rendered.text)
    assert rendered.channel is ResponseChannel.TEXT_AND_VOICE
    assert not requests

    answers = coordinator.observe(
        TranscriptUpdate(1, "Telegram", TranscriptStatus.FINAL, "en")
    )
    resolution = next(
        event for event in answers if isinstance(event, CommandResolution)
    )
    assert resolution.intent == CommandIntent(CommandKind.OPEN_CHAT, target, "telegram")
    outputs = dispatch_command_action(resolution, gate, Executor())
    assert len(outputs) == 1 and isinstance(outputs[0], ActionFeedback)
    assert len(requests) == 1
    assert requests[0].language == "en" and requests[0].intent.target == target
    feedback = presenter.present(outputs[0])
    assert feedback.language == "en"
    assert not re.search(r"[\u0600-\u06ff]", feedback.text.replace(target, "TARGET"))
    if outcome in {ActionOutcome.FAILED, ActionOutcome.UNKNOWN}:
        assert target in feedback.text
    assert outputs[0].outcome is outcome

    # Queue the actual English clarification using an inert voice implementation.
    speaker = ResponseSpeaker(Voice(), on_error=lambda error: pytest.fail(str(error)))
    try:
        assert speaker.submit(rendered)
        assert speaker.wait_until_idle(2)
        assert spoken == [(rendered.text, "en")]
    finally:
        speaker.close()


@pytest.mark.parametrize(
    ("language", "text"),
    [("en", "Do not open Telegram"), ("fa", "تلگرام را باز نکن")],
)
def test_retained_language_grammars_do_not_authorize_negated_requests(
    language: str, text: str
) -> None:
    coordinator = CommandCoordinator(DemoCommandInterpreter())
    gate = ActionGate(ActionPolicy(allowed_apps=frozenset({"telegram"})))
    events = coordinator.observe(
        TranscriptUpdate(0, text, TranscriptStatus.FINAL, language)
    )
    assert events
    assert all(not dispatch_command_action(event, gate, None) for event in events)
