"""Observed window-operation spellings keep exact targets and state distinctions."""

from unittest.mock import Mock

import pytest

from kyrin.commands.app_names import SpokenAppCandidate, SpokenAppMatch
from kyrin.commands.coordinator import CommandCoordinator
from kyrin.commands.demo_interpreter import DemoCommandInterpreter
from kyrin.commands.interpreter import ReadyCommand
from kyrin.commands.models import CommandContext, CommandKind, CommandResolution
from kyrin.stt.transcript import TranscriptStatus, TranscriptUpdate
from scripts.commands.evaluate_l04_baseline import fixture


@pytest.mark.parametrize(
    ("text", "kind"),
    [
        ("Un-Maximize Browser.", CommandKind.UNMAXIMIZE_APP),
        ("Un maximize Browser.", CommandKind.UNMAXIMIZE_APP),
        ("Full Screen Browser", CommandKind.FULLSCREEN_APP),
        ("Full Screen, Browser.", CommandKind.FULLSCREEN_APP),
        ("Full-screen Browser", CommandKind.FULLSCREEN_APP),
        ("Exit Fullscreen Browser.", CommandKind.UNFULLSCREEN_APP),
        ("Exit Full Screen Browser.", CommandKind.UNFULLSCREEN_APP),
        ("Exit Full Screen on Browser.", CommandKind.UNFULLSCREEN_APP),
        ("Minimize Browser.", CommandKind.MINIMIZE_APP),
        ("Unmaximize Browser.", CommandKind.UNMAXIMIZE_APP),
    ],
)
def test_clear_window_spellings_use_direct_exact_operation(
    text: str, kind: CommandKind
) -> None:
    _, rules = fixture()
    result = rules.interpret(
        text, language="en", context=CommandContext(), pending=None
    )
    assert isinstance(result, ReadyCommand)
    assert result.intent.kind is kind
    assert result.intent.target == "browser"


@pytest.mark.parametrize(
    "text",
    [
        "Do not Full Screen Browser.",
        "Never Un-Maximize Browser.",
        'The words "Full Screen Browser" are on the screen.',
        '"Un-Maximize Browser"',
        "What does Full Screen Browser mean?",
        "Type Un-Maximize Browser.",
        "Full Screen Browser or Telegram.",
        "Un-Maximize Unknown Target.",
        "Full Screen Unknown Target.",
        "Exit Fullscreen Unknown Target.",
        "Un-Maximize",
        "Full Screen",
        "Exit Fullscreen",
        "Exit",
    ],
)
def test_window_spelling_does_not_supply_missing_target_or_content_authority(
    text: str,
) -> None:
    _, rules = fixture()
    result = rules.interpret(
        text,
        language="en",
        context=CommandContext(observed_active_app="browser"),
        pending=None,
    )
    assert not isinstance(result, ReadyCommand)


def test_only_operation_span_is_canonicalized_not_literal_app_name() -> None:
    names = Mock()
    names.resolve.return_value = SpokenAppMatch(
        (SpokenAppCandidate("browser", "Full Screen Un-Maximize Lab"),), exact=True
    )
    rules = DemoCommandInterpreter(
        names, allowed_window_apps=frozenset({"browser"})
    )
    result = rules.interpret(
        "Full Screen, Full Screen Un-Maximize Lab.",
        language="en", context=CommandContext(), pending=None,
    )
    assert isinstance(result, ReadyCommand)
    assert result.intent.kind is CommandKind.FULLSCREEN_APP
    names.resolve.assert_called_once_with("full screen un-maximize lab")


def test_literal_search_payload_is_not_canonicalized() -> None:
    _, rules = fixture()
    result = rules.interpret(
        "Search for Full Screen Un-Maximize Lab",
        language="en", context=CommandContext(observed_active_app="telegram"),
        pending=None,
    )
    assert isinstance(result, ReadyCommand)
    assert result.intent.kind is CommandKind.TELEGRAM_SEARCH
    assert result.intent.target == "Full Screen Un-Maximize Lab"


def test_new_window_spelling_remains_final_only() -> None:
    _, rules = fixture()
    coordinator = CommandCoordinator(rules)
    partial = coordinator.observe(
        TranscriptUpdate(0, "Full Screen Browser", TranscriptStatus.PARTIAL, "en")
    )
    assert not any(isinstance(e, CommandResolution) for e in partial)
    final = coordinator.observe(
        TranscriptUpdate(0, "Full Screen Browser", TranscriptStatus.FINAL, "en")
    )
    commands = [e.intent for e in final if isinstance(e, CommandResolution)]
    assert len(commands) == 1
    assert commands[0] is not None
    assert commands[0].kind is CommandKind.FULLSCREEN_APP
