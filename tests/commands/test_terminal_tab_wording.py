"""Tab wording stays contextual and explains an unavailable multiwindow target."""

import pytest

from kyrin.commands.coordinator import CommandCoordinator
from kyrin.commands.interpreter import ReadyCommand
from kyrin.commands.models import (
    CommandContext,
    CommandIntent,
    CommandKind,
    CommandResolution,
    ResponseRequest,
)
from kyrin.responses.presenter import ResponsePresenter
from kyrin.stt.transcript import TranscriptStatus, TranscriptUpdate
from scripts.commands.evaluate_l04_baseline import fixture


@pytest.mark.parametrize("count", [1, 3])
@pytest.mark.parametrize("text", ["New tab", "Create new tab", "Create a new tab"])
def test_exact_tab_wording_never_selects_an_ambiguous_window(
    count: int, text: str
) -> None:
    _, rules = fixture(count)
    owner = CommandCoordinator(rules)
    owner.observe(TranscriptUpdate(0, "Open Terminal", TranscriptStatus.FINAL, "en"))
    events = owner.observe(TranscriptUpdate(1, text, TranscriptStatus.FINAL, "en"))
    assert isinstance(events[0], CommandResolution)
    assert events[0].intent == (
        CommandIntent(CommandKind.NEW_APP_TAB, "terminal") if count == 1 else None
    )
    if count != 1:
        assert owner.pending_clarification is not None


@pytest.mark.parametrize(
    "text", ["Create new tab", "Create a new tab", "News Hub", "Great new tab"]
)
def test_no_out_of_menu_target_or_transcript_replacement(text: str) -> None:
    _, rules = fixture(1)
    assert not isinstance(
        rules.interpret(
            text,
            language="en",
            context=CommandContext(last_referenced_app="terminal"),
            pending=None,
        ),
        ReadyCommand,
    )


@pytest.mark.parametrize("locale", ["en", "fa"])
def test_multiple_window_menu_explains_why_tab_is_unavailable(locale: str) -> None:
    _, rules = fixture(3)
    owner = CommandCoordinator(rules)
    events = owner.observe(
        TranscriptUpdate(0, "Open Terminal", TranscriptStatus.FINAL, locale)
    )
    question = next(e for e in events if isinstance(e, ResponseRequest))
    assert CommandKind.NEW_APP_TAB not in question.operation_candidates
    text = ResponsePresenter(locale).present(question).text
    assert ("exactly one" if locale == "en" else "فقط یک پنجره") in text
    assert ("New window" if locale == "en" else "پنجرهٔ تازه") in text


def test_reopening_same_terminal_menu_refreshes_count_without_model() -> None:
    from kyrin.commands.demo_interpreter import DemoCommandInterpreter
    from kyrin.commands.speech_recovery import SpeechRecoveryInterpreter
    from scripts.commands.evaluate_l04_baseline import FixedPresence
    from tests.commands.test_terminal_menu_speech import final, menu, selected

    owner, model = menu(3)
    owner.observe(final(0, "Open Terminal"))
    owner.observe(final(1, "New tab"))
    # Independently supplied platform observation changes after owner setup.
    assert isinstance(owner.interpreter, SpeechRecoveryInterpreter)
    rules = owner.interpreter.recovery.rules
    assert isinstance(rules, DemoCommandInterpreter)
    rules._window_presence = FixedPresence(1)
    owner.observe(final(2, "Open Terminal"))
    assert selected(owner.observe(final(3, "Create new tab"))) == CommandIntent(
        CommandKind.NEW_APP_TAB, "terminal"
    )
    model.understand.assert_not_called()
