"""Application previews require a fresh filtered picker and explicit selection."""

from unittest.mock import Mock

import pytest

from kyrin.commands.app_names import SpokenAppCandidate, SpokenAppMatch
from kyrin.commands.coordinator import CommandCoordinator
from kyrin.commands.demo_interpreter import DemoCommandInterpreter
from kyrin.commands.interpreter import NeedsClarification, ReadyCommand
from kyrin.commands.models import (
    CommandContext,
    CommandIntent,
    CommandKind,
    CommandResolution,
    PendingWindowSelection,
    ResponseKind,
    ResponseRequest,
)
from kyrin.stt.transcript import TranscriptStatus, TranscriptUpdate
from scripts.commands.evaluate_l04_baseline import fixture


def final(index: int, text: str) -> TranscriptUpdate:
    return TranscriptUpdate(index, text, TranscriptStatus.FINAL, "en")


@pytest.mark.parametrize("text", ["Show Browser windows", "Show Browser's windows"])
def test_explicit_app_preview_then_number_uses_current_shared_snapshot(
    text: str,
) -> None:
    _, rules = fixture(2)
    coordinator = CommandCoordinator(rules)
    shown = coordinator.observe(final(0, text))
    assert isinstance(shown[0], CommandResolution)
    assert shown[0].intent == CommandIntent(CommandKind.SHOW_APP_WINDOWS, "browser")
    assert isinstance(shown[1], ResponseRequest)
    assert shown[1].kind is ResponseKind.CHOOSE_WINDOW
    assert shown[1].window_count == 2
    selected = coordinator.observe(final(1, "Number two"))
    assert isinstance(selected[0], CommandResolution)
    assert selected[0].intent == CommandIntent(
        CommandKind.SELECT_APP_WINDOW, "desktop", window_index=2
    )


def test_named_multiwindow_app_narrows_picker_without_activating_a_guess() -> None:
    _, rules = fixture(2)
    coordinator = CommandCoordinator(rules)
    coordinator.observe(final(0, "Show all open windows"))
    narrowed = coordinator.observe(final(1, "Browser"))
    assert isinstance(narrowed[0], CommandResolution)
    assert narrowed[0].intent == CommandIntent(CommandKind.SHOW_APP_WINDOWS, "browser")
    assert isinstance(coordinator.pending_clarification, PendingWindowSelection)
    assert coordinator.pending_clarification.all_apps is False
    cancelled = coordinator.observe(final(2, "Cancel"))
    assert isinstance(cancelled[0], CommandResolution)
    assert cancelled[0].intent == CommandIntent(CommandKind.HIDE_APP_WINDOWS, "desktop")


def test_named_single_window_keeps_exact_snapshot_activation() -> None:
    _, rules = fixture(1)
    coordinator = CommandCoordinator(rules)
    coordinator.observe(final(0, "Show all open windows"))
    chosen = coordinator.observe(final(1, "Browser"))
    assert isinstance(chosen[0], CommandResolution)
    assert chosen[0].intent == CommandIntent(
        CommandKind.SELECT_OPEN_APP_WINDOW, "browser"
    )


def test_model_app_preview_gets_same_bounded_numbered_followup() -> None:
    _, rules = fixture(2)
    result = rules.review_model_action(
        CommandIntent(CommandKind.SHOW_APP_WINDOWS, "browser"), CommandContext()
    )
    assert isinstance(result, ReadyCommand)
    assert isinstance(result.follow_up, PendingWindowSelection)
    assert result.follow_up.app_candidate.app_id == "desktop"
    assert result.follow_up.count == 2


@pytest.mark.parametrize(
    "text",
    [
        "Do not show Browser windows",
        'The words "Show Browser windows" are on screen',
        "Show Browser or Telegram windows",
        "Show Unknown windows",
    ],
)
def test_preview_never_infers_missing_or_negated_target(text: str) -> None:
    _, rules = fixture(2)
    result = rules.interpret(
        text, language="en", context=CommandContext(observed_active_app="browser"),
        pending=None,
    )
    assert not isinstance(result, ReadyCommand)


def test_filtered_close_still_asks_separately_and_cancel_closes_nothing() -> None:
    _, rules = fixture(2)
    coordinator = CommandCoordinator(rules)
    coordinator.observe(final(0, "Show Browser windows"))
    close = coordinator.observe(final(1, "Close number two"))
    assert isinstance(close[0], CommandResolution) and close[0].intent is None
    assert isinstance(close[1], ResponseRequest)
    assert close[1].kind is ResponseKind.CONFIRM_NUMBERED_CLOSE
    declined = coordinator.observe(final(2, "No"))
    assert isinstance(declined[0], CommandResolution) and declined[0].intent is None


def test_preview_partial_does_not_create_number_selection_context() -> None:
    _, rules = fixture(2)
    coordinator = CommandCoordinator(rules)
    events = coordinator.observe(
        TranscriptUpdate(0, "Show Browser windows", TranscriptStatus.PARTIAL, "en")
    )
    assert not any(isinstance(event, CommandResolution) for event in events)
    assert coordinator.pending_clarification is None


def test_partial_preview_does_not_query_platform_window_count() -> None:
    _, rules = fixture(2)
    presence = Mock()
    rules._window_presence = presence
    rules.interpret(
        "Show Browser windows", language="en",
        context=CommandContext(is_final_transcript=False), pending=None,
    )
    presence.count.assert_not_called()


@pytest.mark.parametrize("count", [0, None])
def test_missing_or_unknown_windows_do_not_create_picker_context(
    count: int | None,
) -> None:
    _, rules = fixture(count)
    result = rules.interpret(
        "Show Browser windows", language="en", context=CommandContext(), pending=None
    )
    assert not isinstance(result, ReadyCommand)


def test_literal_possessive_app_and_possessive_syntax_are_not_guessed() -> None:
    names = Mock()
    names.resolve.side_effect = lambda name: SpokenAppMatch(
        (SpokenAppCandidate(name, name),), exact=True
    )
    rules = DemoCommandInterpreter(
        names, allowed_window_apps=frozenset({"browser's", "browser"})
    )
    result = rules.interpret(
        "Show Browser's windows", language="en", context=CommandContext(), pending=None
    )
    assert isinstance(result, NeedsClarification)
    assert not isinstance(result, ReadyCommand)
