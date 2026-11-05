"""Polite operation prefixes and explicit chat apps retain source roles."""

import pytest

from kyrin.commands.demo_interpreter import DemoCommandInterpreter
from kyrin.commands.interpreter import ReadyCommand
from kyrin.commands.models import CommandContext
from kyrin.commands.operation_verifier import RuleBasedOperationEvidence
from kyrin.commands.understanding import RequestedOperation
from scripts.commands.evaluate_l04_baseline import fixture


@pytest.mark.parametrize(
    ("text", "operation"),
    [
        ("Would you restore Browser?", RequestedOperation.RESTORE_APP),
        ("Could you minimize Telegram?", RequestedOperation.MINIMIZE_APP),
        ("Can you please close Browser?", RequestedOperation.CLOSE_APP_WINDOW),
        ("Please could you fullscreen Telegram?", RequestedOperation.FULLSCREEN_APP),
    ],
)
def test_polite_app_requests_retain_independent_operation_evidence(
    text: str, operation: RequestedOperation
) -> None:
    evidence = RuleBasedOperationEvidence().extract(text, language="en")
    assert evidence.reason is None
    assert evidence.operations == (operation,)


@pytest.mark.parametrize(
    "text",
    [
        "Could you not close Browser?",
        "Would you type close Browser?",
        'Could you say "close Browser"?',
        "Would you close Browser or Telegram?",
    ],
)
def test_polite_prefix_never_supplies_negated_quoted_or_alternative_authority(
    text: str,
) -> None:
    assert RuleBasedOperationEvidence().extract(text, language="en").reason is not None


@pytest.mark.parametrize(
    ("text", "name"),
    [
        ("Open chat Review Group in Telegram.", "Review Group"),
        ("Open Review Group chat in Telegram.", "Review Group"),
        ("Open chat مینا Test in Telegram.", "مینا Test"),
    ],
)
def test_explicit_chat_app_is_separate_from_literal_chat_name(
    text: str, name: str
) -> None:
    _, rules = fixture()
    result = rules.interpret(
        text,
        language="en",
        context=CommandContext(observed_active_app="browser"),
        pending=None,
    )
    assert isinstance(result, ReadyCommand)
    assert result.intent.kind.value == "open_chat"
    assert result.intent.target == name
    assert result.intent.app == "telegram"


def test_explicit_chat_app_wins_over_conflicting_current_app() -> None:
    result = DemoCommandInterpreter().interpret(
        "Open chat Review Group in WhatsApp",
        language="en",
        context=CommandContext(observed_active_app="telegram"),
        pending=None,
    )
    assert isinstance(result, ReadyCommand)
    assert result.intent.target == "Review Group"
    assert result.intent.app == "whatsapp"


def test_chat_title_internal_preposition_is_not_rewritten() -> None:
    _, rules = fixture()
    result = rules.interpret(
        "Open chat Night in Paris in Telegram",
        language="en",
        context=CommandContext(observed_active_app="browser"),
        pending=None,
    )
    assert isinstance(result, ReadyCommand)
    assert result.intent.target == "Night in Paris"
    assert result.intent.app == "telegram"


@pytest.mark.parametrize("app", ["Browser", "Unknown Messenger"])
def test_unknown_or_unsupported_explicit_chat_app_never_uses_current_app(
    app: str,
) -> None:
    _, rules = fixture()
    result = rules.interpret(
        "Open chat Review Group in " + app,
        language="en",
        context=CommandContext(observed_active_app="telegram"),
        pending=None,
    )
    assert not isinstance(result, ReadyCommand)
