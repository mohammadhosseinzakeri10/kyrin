"""Spoken chat selection stays bounded and waits for an explicit answer."""

from threading import Event

import pytest

from kyrin.actions.models import ActionKey, ActionOutcome, ActionRequest, ActionResult
from kyrin.actions.telegram_selection import TelegramChatSelection
from kyrin.actions.telegram_verification import ChatSearchChoices, ChatSearchMatch
from kyrin.commands.models import CommandIntent, CommandKind, ResponseRequest


def _request() -> ActionRequest:
    return ActionRequest(
        ActionKey(0, 3), CommandIntent(CommandKind.OPEN_CHAT, "My Mother", "telegram"),
        "en",
    )


def _choices() -> ChatSearchChoices:
    return ChatSearchChoices(
        ChatSearchMatch(70, 92, 90, 13, 1600, 900),
        (),
        (ChatSearchMatch(70, 154, 90, 13, 1600, 900),),
    )


def test_invalid_answer_repeats_prompt_without_clicking() -> None:
    prompts: list[ResponseRequest] = []
    calls: list[int | None] = []
    flow = TelegramChatSelection(prompts.append, lambda _: None)

    def complete(request, identity, target, choices, number, cancellation):
        calls.append(number)
        return ActionResult(request.key, ActionOutcome.CONFIRMED)

    flow.set_completion(complete)
    assert flow.begin(_request(), ("telegram.desktop", 12), "My Mother", _choices())
    assert flow.on_final_speech("something else")
    assert len(prompts) == 2
    assert calls == []
    assert flow.on_final_speech("cancel")
    assert not flow.on_final_speech("one")
    assert not flow.on_final_speech("non-bear too")
    assert not flow.on_final_speech("nombertoo")
    assert calls == []


def test_new_visible_chat_command_replaces_pending_numbered_choice() -> None:
    prompts: list[ResponseRequest] = []
    feedback = []
    flow = TelegramChatSelection(prompts.append, feedback.append)
    flow.set_completion(lambda *args: pytest.fail("old chat must not be opened"))
    assert flow.begin(_request(), ("telegram.desktop", 12), "My Mother", _choices())

    assert not flow.on_final_speech("openvisibly chat shop vimes")
    assert [item.error_code for item in feedback] == ["chat_selection_cancelled"]
    assert len(prompts) == 1
    assert not flow.on_final_speech("first")


def test_duplicate_chat_choice_requires_a_valid_number() -> None:
    prompts: list[ResponseRequest] = []
    calls: list[int | None] = []
    done = Event()
    flow = TelegramChatSelection(prompts.append, lambda _: done.set())

    def complete(request, identity, target, choices, number, cancellation):
        calls.append(number)
        return ActionResult(request.key, ActionOutcome.CONFIRMED)

    flow.set_completion(complete)
    assert flow.begin(_request(), ("telegram.desktop", 12), "My Mother", _choices())
    assert flow.on_final_speech("number three")
    assert len(prompts) == 2
    assert calls == []
    assert flow.on_final_speech("number two")
    assert done.wait(2)
    assert calls == [2]
    assert not flow.on_final_speech("number one")


@pytest.mark.parametrize(
    ("answer", "expected"),
    [
        ("one", 1), ("Number 1.", 1), ("the first", 1), ("first one", 1),
        ("two", 2), ("number two", 2), ("the second", 2),
        ("non-bear too", 2), ("nombertoo", 2),
        ("nomber two", 2), ("nomber 2", 2),
        ("THE SECOND ONE!", 2), ("second option", 2), ("the 2nd", 2),
        ("option number two", 2), ("choose the second", 2),
        ("select option 2", 2), ("pick the second chat", 2),
        ("three", 3), ("number three", 3), ("the third", 3),
        ("third result", 3), ("3rd", 3), ("option 3", 3),
        ("۲", 2), ("شماره دو", 2), ("شمارهٔ دو", 2), ("گزینه دوم", 2),
        ("  the   second  ", 2),
    ],
)
def test_choice_forms_select_the_same_number(answer: str, expected: int) -> None:
    calls: list[int | None] = []
    done = Event()
    flow = TelegramChatSelection(lambda _: None, lambda _: done.set())

    def complete(request, identity, target, choices, number, cancellation):
        calls.append(number)
        return ActionResult(request.key, ActionOutcome.CONFIRMED)

    flow.set_completion(complete)
    choices = ChatSearchChoices(
        _choices().own_chat, (),
        (*_choices().other_local_results,
         ChatSearchMatch(70, 216, 90, 13, 1600, 900)),
    )
    assert flow.begin(_request(), ("telegram.desktop", 12), "My Mother", choices)
    try:
        assert flow.on_final_speech(answer)
        assert done.wait(2)
        assert calls == [expected]
    finally:
        flow.cancel()


@pytest.mark.parametrize(
    "answer",
    [
        "one or two", "the first and second", "not the second", "don't pick two",
        "second, no first", "two chats", "2st", "0", "the third", "eleventh",
        "گزینه اول یا دوم", "", "the", "number",
        "not non-bear too", "nombertoo or one", "nomber two or one",
    ],
)
def test_ambiguous_or_unavailable_choice_never_completes(answer: str) -> None:
    prompts: list[ResponseRequest] = []
    flow = TelegramChatSelection(prompts.append, lambda _: None)
    flow.set_completion(lambda *args: pytest.fail("no chat should be selected"))
    assert flow.begin(_request(), ("telegram.desktop", 12), "My Mother", _choices())
    try:
        assert flow.on_final_speech(answer)
        assert len(prompts) == 2
    finally:
        flow.cancel()


def test_unanswered_selection_expires_without_new_speech(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import kyrin.actions.telegram_selection as module

    monkeypatch.setattr(module, "_TIMEOUT_SECONDS", 0.03)
    finished = Event()
    feedback = []
    flow = TelegramChatSelection(
        lambda _: None, lambda item: (feedback.append(item), finished.set())
    )
    flow.set_completion(lambda *args: pytest.fail("no chat should be opened"))
    assert flow.begin(_request(), ("telegram.desktop", 12), "My Mother", _choices())
    assert finished.wait(1)
    assert feedback[0].error_code == "chat_selection_expired"
    assert not flow.on_final_speech("one")


def test_stopping_pending_selection_reports_cancellation() -> None:
    feedback = []
    flow = TelegramChatSelection(lambda _: None, feedback.append)
    flow.set_completion(
        lambda *args: ActionResult(_request().key, ActionOutcome.CONFIRMED)
    )
    assert flow.begin(_request(), ("telegram.desktop", 12), "My Mother", _choices())
    flow.cancel()
    assert [item.error_code for item in feedback] == ["chat_selection_cancelled"]
    assert not flow.on_final_speech("one")


def test_global_search_results_alone_do_not_start_chat_selection() -> None:
    prompts: list[ResponseRequest] = []
    flow = TelegramChatSelection(prompts.append, lambda _: None)
    flow.set_completion(
        lambda *args: pytest.fail("global search must not select a chat")
    )
    global_only = ChatSearchChoices(
        None,
        (
            ChatSearchMatch(70, 182, 90, 13, 1600, 900),
            ChatSearchMatch(70, 244, 90, 13, 1600, 900),
        ),
    )
    assert not flow.begin(
        _request(), ("telegram.desktop", 12), "My Mother", global_only
    )
    assert prompts == []
    assert not flow.on_final_speech("one")


def test_verified_global_results_ask_for_a_number() -> None:
    prompts: list[ResponseRequest] = []
    calls: list[int | None] = []
    done = Event()
    flow = TelegramChatSelection(prompts.append, lambda _: done.set())

    def complete(request, identity, target, choices, number, cancellation):
        calls.append(number)
        return ActionResult(request.key, ActionOutcome.CONFIRMED)

    flow.set_completion(complete)
    global_only = ChatSearchChoices(
        None,
        (
            ChatSearchMatch(70, 182, 90, 13, 1600, 900),
            ChatSearchMatch(70, 244, 90, 13, 1600, 900),
        ),
        global_section_verified=True,
    )
    assert flow.begin(
        _request(), ("telegram.desktop", 12), "My Mother", global_only
    )
    assert "global search results" in prompts[0].message
    assert flow.on_final_speech("the second")
    assert done.wait(2)
    assert calls == [2]


def test_next_results_replaces_visible_numbered_page() -> None:
    prompts: list[ResponseRequest] = []
    reprompted = Event()
    selected = Event()
    chosen_tops: list[int] = []

    def prompt(item: ResponseRequest) -> None:
        prompts.append(item)
        if len(prompts) == 2:
            reprompted.set()

    flow = TelegramChatSelection(prompt, lambda _: selected.set())
    later = ChatSearchChoices(
        ChatSearchMatch(70, 230, 90, 13, 1600, 900),
        (),
        (ChatSearchMatch(70, 292, 90, 13, 1600, 900),),
        view_signature="next-page",
    )
    flow.set_page_navigation(lambda *_args: later)

    def complete(request, identity, target, choices, number, cancellation):
        chosen_tops.append(choices.selectable_results[number - 1].top)
        return ActionResult(request.key, ActionOutcome.CONFIRMED)

    flow.set_completion(complete)
    assert flow.begin(_request(), ("telegram.desktop", 12), "My Mother", _choices())
    assert flow.on_final_speech("next")
    assert reprompted.wait(2)
    assert flow.on_final_speech("number two")
    assert selected.wait(2)
    assert chosen_tops == [292]
    assert "personal chats" in prompts[1].message


def test_global_next_page_keeps_global_wording() -> None:
    prompts: list[ResponseRequest] = []
    second_prompt = Event()

    def prompt(item: ResponseRequest) -> None:
        prompts.append(item)
        if len(prompts) == 2:
            second_prompt.set()

    flow = TelegramChatSelection(prompt, lambda _: None)
    first = ChatSearchChoices(
        None, (ChatSearchMatch(70, 182, 90, 13, 1600, 900),),
        global_section_verified=True, view_signature="first",
    )
    later = ChatSearchChoices(
        None, (ChatSearchMatch(70, 92, 90, 13, 1600, 900),),
        global_section_verified=True, view_signature="later",
    )
    flow.set_completion(lambda *args: pytest.fail("no selection expected"))
    flow.set_page_navigation(lambda *_args: later)
    assert flow.begin(_request(), ("telegram.desktop", 12), "My Mother", first)
    assert flow.on_final_speech("next")
    assert second_prompt.wait(2)
    assert "global search results" in prompts[1].message
    flow.cancel()


def test_spoken_cancel_while_paging_stops_the_prompt() -> None:
    prompts: list[ResponseRequest] = []
    feedback = []
    started = Event()
    release = Event()
    finished = Event()
    flow = TelegramChatSelection(
        prompts.append,
        lambda item: (feedback.append(item), finished.set()),
    )
    flow.set_completion(lambda *args: pytest.fail("no chat should be clicked"))

    def navigate(identity, target, choices, cancellation):
        started.set()
        assert release.wait(2)
        return _choices()

    flow.set_page_navigation(navigate)
    assert flow.begin(_request(), ("telegram.desktop", 12), "My Mother", _choices())
    assert flow.on_final_speech("next")
    assert started.wait(2)
    assert flow.on_final_speech("cancel")
    release.set()
    assert finished.wait(2)
    assert feedback[0].error_code == "chat_selection_cancelled"
    assert len(prompts) == 1


def test_spoken_cancel_during_click_reports_actual_result() -> None:
    feedback = []
    started = Event()
    release = Event()
    finished = Event()
    flow = TelegramChatSelection(
        lambda _: None,
        lambda item: (feedback.append(item), finished.set()),
    )

    def complete(request, identity, target, choices, number, cancellation):
        started.set()
        assert release.wait(2)
        # A click already sent to Telegram cannot be undone by speech.
        return ActionResult(request.key, ActionOutcome.LAUNCH_ACCEPTED)

    flow.set_completion(complete)
    assert flow.begin(_request(), ("telegram.desktop", 12), "My Mother", _choices())
    assert flow.on_final_speech("number one")
    assert started.wait(2)
    assert flow.on_final_speech("cancel")
    release.set()
    assert finished.wait(2)
    assert feedback[0].outcome is ActionOutcome.LAUNCH_ACCEPTED
