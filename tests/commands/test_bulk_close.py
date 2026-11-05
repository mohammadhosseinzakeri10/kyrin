"""Bulk close requires an exact app and explicit all scope, never model repair."""

from unittest.mock import Mock

import pytest

from kyrin.commands.coordinator import CommandCoordinator
from kyrin.commands.interpreter import ReadyCommand
from kyrin.commands.model_interpreter import ModelAssistedInterpreter
from kyrin.commands.models import CommandContext, CommandIntent, CommandKind
from kyrin.stt.transcript import TranscriptStatus, TranscriptUpdate
from scripts.commands.evaluate_l04_baseline import fixture


@pytest.mark.parametrize("app", ["Browser", "School", "Telegram"])
@pytest.mark.parametrize(
    "template", ["Close all {}.", "Please close all windows of {}."]
)
def test_bulk_close_exact_catalog_scope(app: str, template: str) -> None:
    _, rules = fixture(2)
    result = rules.interpret(
        template.format(app), language="en", context=CommandContext(), pending=None
    )
    assert isinstance(result, ReadyCommand)
    assert result.intent == CommandIntent(
        CommandKind.CLOSE_ALL_APP_WINDOWS, app.lower()
    )


@pytest.mark.parametrize(
    "text",
    [
        "Close all",
        "Close all Unknown",
        "Close all Browsr",
        "Close all Browser and School",
        "Close all windows",
        "Close all Browser except one",
        "Close all Browser or School",
        "Do not close all Browser",
        'The words "Close all Browser" are on screen',
    ],
)
def test_bulk_scope_cannot_guess_a_target_or_execute_content(text: str) -> None:
    names, rules = fixture(2)
    model = Mock()
    model.understand.side_effect = AssertionError("exact bulk source cannot call model")
    base = ModelAssistedInterpreter(
        rules,
        model,
        names,
        allowed_apps=frozenset({"browser", "school"}),
        supported_chat_apps=frozenset(),
        action_review=rules.review_model_action,
    )
    result = base.interpret(text, language="en", context=CommandContext(), pending=None)
    assert not isinstance(result, ReadyCommand)


def test_bulk_close_partial_and_missing_permission_never_authorize() -> None:
    _, rules = fixture(2)
    owner = CommandCoordinator(rules)
    owner.observe(
        TranscriptUpdate(0, "Close all Browser", TranscriptStatus.PARTIAL, "en")
    )
    assert owner.pending_clarification is None
    rules._allowed_close_apps = frozenset()
    result = rules.interpret(
        "Close all Browser", language="en", context=CommandContext(), pending=None
    )
    assert not isinstance(result, ReadyCommand)


def test_single_close_remains_distinct() -> None:
    _, rules = fixture(2)
    result = rules.interpret(
        "Close Browser", language="en", context=CommandContext(), pending=None
    )
    assert isinstance(result, ReadyCommand)
    assert result.intent.kind is CommandKind.CLOSE_APP_WINDOW


def test_literal_all_app_name_cannot_silently_become_bulk_scope() -> None:
    from kyrin.commands.app_names import SpokenAppCandidate, SpokenAppMatch

    _, rules = fixture(2)
    names = Mock()
    names.resolve.side_effect = lambda value: SpokenAppMatch(
        (SpokenAppCandidate(value, value),), exact=True
    )
    rules._app_name_resolver = names
    assert not isinstance(rules.interpret(
        "Close all Browser", language="en", context=CommandContext(), pending=None,
    ), ReadyCommand)
