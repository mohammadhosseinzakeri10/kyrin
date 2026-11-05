"""Focused tabs and one-use numbered continuations, with no native action."""

from dataclasses import replace
from time import monotonic

import pytest

from kyrin.commands.coordinator import CommandCoordinator
from kyrin.commands.demo_interpreter import DemoCommandInterpreter
from kyrin.commands.models import CommandKind, CommandResolution, PendingWindowSelection
from kyrin.desktop.window_observation import WindowObservation
from kyrin.stt.evidence import SpeechEvidence, SpeechHypothesis
from kyrin.stt.transcript import TranscriptStatus, TranscriptUpdate
from scripts.commands.evaluate_l04_baseline import FixedPresence, fixture
from tests.commands.test_terminal_menu_speech import menu


def observe(
    owner: CommandCoordinator,
    n: int,
    text: str,
    *,
    focused: bool = False,
    status: TranscriptStatus = TranscriptStatus.FINAL,
) -> CommandResolution | None:
    events = owner.observe(
        TranscriptUpdate(n, text, status, "en"),
        observed_active_app="terminal" if focused else "browser",
        observed_scroll_app="org.gnome.Ptyxis.desktop"
        if focused
        else "browser.desktop",
    )
    return next((e for e in events if isinstance(e, CommandResolution)), None)


def owner(count: int = 2) -> CommandCoordinator:
    names, _ = fixture(count)
    rules = DemoCommandInterpreter(
        names,
        allowed_window_apps=frozenset({"terminal"}),
        window_presence=FixedPresence(count),
        terminal_app_id="terminal",
        control_any_focused_app=True,
        targeted_terminal_tabs=True,
    )
    now = monotonic()
    window = WindowObservation(
        "org.gnome.Ptyxis.desktop", 5, "window-one", "obs", now, now + 10
    )
    return CommandCoordinator(rules, window_observer=lambda: window)


@pytest.mark.parametrize("phrase", ["New tab", "Create new tab", "Create a new tab"])
def test_focused_terminal_is_bound_even_with_multiple_windows(phrase: str) -> None:
    result = observe(owner(), 0, phrase, focused=True)
    assert result is not None and result.intent is not None
    assert result.intent.kind is CommandKind.NEW_APP_TAB
    assert result.intent.tab_observation is not None
    assert result.intent.tab_observation.window_token == "window-one"
    assert result.intent.tab_selection_id is None


@pytest.mark.parametrize("count", [1, 2, 3])
def test_unfocused_tab_asks_and_number_continues_original_operation(count: int) -> None:
    o = owner(count)
    shown = observe(o, 0, "New tab")
    assert shown and shown.intent and shown.intent.kind is CommandKind.SHOW_APP_WINDOWS
    generation = shown.intent.tab_selection_id
    assert generation and isinstance(o.pending_clarification, PendingWindowSelection)
    selected = observe(o, 1, "First")
    assert (
        selected and selected.intent and selected.intent.kind is CommandKind.NEW_APP_TAB
    )
    assert selected.intent.window_index == 1
    assert selected.intent.tab_selection_id == generation
    assert o.pending_clarification is None
    # A repeated number cannot create another tab.
    again = observe(o, 2, "First")
    assert again is None or again.intent is None


@pytest.mark.parametrize("case", ["cancel", "expiry", "partial", "stop"])
def test_tab_choice_does_not_survive_rejection_or_expiry(case: str) -> None:
    o = owner()
    observe(o, 0, "New tab")
    if case == "cancel":
        result = observe(o, 1, "Cancel")
        assert (
            result
            and result.intent
            and result.intent.kind is CommandKind.HIDE_APP_WINDOWS
        )
    elif case == "expiry":
        pending = o.pending_clarification
        assert isinstance(pending, PendingWindowSelection)
        o._pending = replace(pending, deadline=monotonic() - 1)
    elif case == "partial":
        assert observe(o, 1, "First", status=TranscriptStatus.PARTIAL) is None
        return
    else:
        o.cancel_dialogue()
    result = observe(o, 2, "First")
    assert result is None or result.intent is None


@pytest.mark.parametrize(
    "phrase",
    [
        "Do not create a new tab",
        'The words "new tab" are on the screen',
        "News Hub",
        "Great new tab",
    ],
)
def test_free_text_negation_and_observed_misrecognitions_never_authorize_tab(
    phrase: str,
) -> None:
    result = observe(owner(), 0, phrase, focused=True)
    assert result is None or result.intent is None


def test_speech_wrapper_keeps_same_picker_generation_across_hypotheses() -> None:
    o, model = menu(2)
    rules = o.interpreter.recovery.rules  # type: ignore[attr-defined]
    assert isinstance(rules, DemoCommandInterpreter)
    rules._targeted_terminal_tabs = True
    result = o.observe(
        TranscriptUpdate(
            0,
            "New tab",
            TranscriptStatus.FINAL,
            "en",
            evidence=SpeechEvidence(
                "test", (SpeechHypothesis("Create a new tab", "test"),)
            ),
        )
    )
    resolution = next(e for e in result if isinstance(e, CommandResolution))
    assert resolution.intent and resolution.intent.kind is CommandKind.SHOW_APP_WINDOWS
    model.understand.assert_not_called()


def test_fresh_tab_request_after_mouse_focus_uses_current_window() -> None:
    o = owner()
    observe(o, 0, "New tab")
    result = observe(o, 1, "New tab", focused=True)
    assert result and result.intent and result.intent.tab_observation
    assert result.intent.tab_selection_id is None
