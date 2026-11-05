"""Chat selection reports its actual stage and keeps display language separate."""

from dataclasses import replace
from threading import Event

import pytest

from kyrin.actions.models import (
    ActionFeedback,
    ActionKey,
    ActionOutcome,
    ActionRequest,
    ActionResult,
)
from kyrin.actions.telegram_selection import TelegramChatSelection
from kyrin.actions.telegram_verification import ChatSearchChoices, ChatSearchMatch
from kyrin.commands.models import CommandIntent, CommandKind, ResponseRequest
from kyrin.responses.presenter import ResponsePresenter
from kyrin.responses.visual_status import (
    VisualPresentation,
    VisualStatus,
    VisualStatusController,
)
from kyrin.stt.transcript import TranscriptStatus, TranscriptUpdate


def _request() -> ActionRequest:
    return ActionRequest(
        ActionKey(0, 3),
        CommandIntent(CommandKind.OPEN_CHAT, "My Mother", "telegram"),
        "en",
    )


def _choices() -> ChatSearchChoices:
    return ChatSearchChoices(
        ChatSearchMatch(70, 92, 90, 13, 1600, 900),
        (),
        (ChatSearchMatch(70, 154, 90, 13, 1600, 900),),
    )


@pytest.mark.parametrize("command_language", ["en", "en-US", "fa-IR", "FA_IR"])
@pytest.mark.parametrize("visual_language", ["en", "fa"])
def test_builtin_chat_question_uses_independent_visual_language(
    command_language: str,
    visual_language: str,
) -> None:
    prompts: list[ResponseRequest] = []
    visuals: list[VisualPresentation] = []
    visual = VisualStatusController(visuals.append, language=visual_language)

    def prompt(event: ResponseRequest) -> None:
        prompts.append(event)
        visual.on_chat_selection_prompt(event)

    flow = TelegramChatSelection(prompt, lambda _: None)
    flow.set_completion(lambda *_: pytest.fail("no selection was authorized"))
    request = replace(_request(), language=command_language)
    try:
        assert flow.begin(request, ("telegram.desktop", 12), "My Mother", _choices())
        assert ("چت شخصی" if visual_language == "fa" else "personal chats") in visuals[
            -1
        ].caption
        spoken = ResponsePresenter("en").present(prompts[-1])
        language = command_language.lower().replace("_", "-").split("-", 1)[0]
        assert spoken.language == language
        assert ("چت" if language == "fa" else "personal chats") in spoken.text
    finally:
        flow.cancel()


def test_selection_and_paging_workers_report_their_actual_start() -> None:
    visuals: list[VisualPresentation] = []
    visual = VisualStatusController(visuals.append)
    reprompted = Event()
    completed = Event()
    prompts: list[ResponseRequest] = []

    def prompt(event: ResponseRequest) -> None:
        prompts.append(event)
        visual.on_chat_selection_prompt(event)
        if len(prompts) > 1:
            reprompted.set()

    def feedback(event: ActionFeedback) -> None:
        visual.on_action_output(event)
        completed.set()

    flow = TelegramChatSelection(
        prompt,
        feedback,
        on_selection_start=visual.on_action_start,
        on_navigation_start=visual.on_chat_navigation_start,
    )
    errors: list[str] = []

    def navigate(*_args: object) -> ChatSearchChoices:
        if (
            visuals[-1].status is not VisualStatus.EXECUTING
            or "more chat choices" not in visuals[-1].caption
        ):
            errors.append("paging caption missing at actual navigation start")
        return _choices()

    def complete(request: ActionRequest, *_args: object) -> ActionResult:
        if (
            visuals[-1].status is not VisualStatus.EXECUTING
            or "Opening chat My Mother" not in visuals[-1].caption
        ):
            errors.append("selection caption missing at actual selection start")
        return ActionResult(request.key, ActionOutcome.CONFIRMED)

    flow.set_completion(complete)
    flow.set_page_navigation(navigate)
    try:
        assert flow.begin(_request(), ("telegram.desktop", 12), "My Mother", _choices())
        assert visuals[-1].status is VisualStatus.QUESTION
        assert flow.on_final_speech("next")
        assert reprompted.wait(2)
        assert visuals[-1].status is VisualStatus.QUESTION
        visual.on_live_event(TranscriptUpdate(4, "one", TranscriptStatus.FINAL))
        assert flow.on_final_speech("one")
        assert completed.wait(2)
        assert not errors
        assert visuals[-1] == VisualPresentation(
            VisualStatus.CONFIRMED, "Open chat My Mother — Done."
        )
    finally:
        flow.cancel()
