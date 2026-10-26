"""Control names retain role words in both rules and model proposals."""

from pathlib import Path

import pytest

from kyrin.commands.demo_interpreter import DemoCommandInterpreter
from kyrin.commands.interpreter import ReadyCommand, UnrecognizedCommand
from kyrin.commands.models import CommandContext
from kyrin.commands.visible_options import VisibleOption
from tests.commands.test_model_interpreter import (
    FakeModel,
    _interpreter,
    _visible_ready,
)


@pytest.mark.parametrize(
    "label", ["Test Button", "Test Option", "Status Icon", "Menu Item"]
)
def test_rules_preserve_complete_control_name(label: str) -> None:
    result = DemoCommandInterpreter(control_any_focused_app=True).interpret(
        f"Click {label}.",
        language="en",
        context=CommandContext(observed_scroll_app="example.desktop"),
        pending=None,
    )
    assert isinstance(result, ReadyCommand)
    assert result.intent.target == label


@pytest.mark.parametrize("target,accepted", [("Test", False), ("Test Button", True)])
def test_model_cannot_substitute_shorter_observed_prefix(
    tmp_path: Path, target: str, accepted: bool
) -> None:
    options = (
        VisibleOption("1", "Test", "accessibility", "button"),
        VisibleOption("2", "Test Button", "accessibility", "button"),
    )
    model = FakeModel(_visible_ready(target, "1" if target == "Test" else "2"))
    interpreter = _interpreter(
        tmp_path, model, visible_options=options, allow_visible_control=True
    )
    result = interpreter.interpret(
        "Could you click Test Button?",
        language="en",
        context=CommandContext(observed_scroll_app="example.desktop"),
        pending=None,
    )
    assert isinstance(result, ReadyCommand if accepted else UnrecognizedCommand)


def test_model_accepts_explicit_role_description_without_renaming(
    tmp_path: Path,
) -> None:
    model = FakeModel(_visible_ready("Test", "1"))
    interpreter = _interpreter(
        tmp_path,
        model,
        visible_options=(VisibleOption("1", "Test", "accessibility", "button"),),
        allow_visible_control=True,
    )
    result = interpreter.interpret(
        "Could you click the button named Test?",
        language="en",
        context=CommandContext(observed_scroll_app="example.desktop"),
        pending=None,
    )
    assert isinstance(result, ReadyCommand) and result.intent.target == "Test"


@pytest.mark.parametrize(
    "verb,state", [("click", None), ("enable", True), ("disable", False)]
)
def test_model_does_not_shorten_missing_full_name_to_an_existing_control(
    tmp_path: Path,
    verb: str,
    state: bool | None,
) -> None:
    interpreter = _interpreter(
        tmp_path,
        FakeModel(_visible_ready("Test", "1", state)),
        visible_options=(
            VisibleOption("1", "Test", "accessibility", "check box", False),
        ),
        allow_visible_control=True,
    )
    assert isinstance(
        interpreter.interpret(
            f"Could you {verb} Test Option?",
            language="en",
            context=CommandContext(observed_scroll_app="example.desktop"),
            pending=None,
        ),
        UnrecognizedCommand,
    )


@pytest.mark.parametrize("verb,state", [("enable", True), ("disable", False)])
def test_state_request_retains_full_name_in_rules_and_model(
    tmp_path: Path,
    verb: str,
    state: bool,
) -> None:
    context = CommandContext(observed_scroll_app="example.desktop")
    rules = DemoCommandInterpreter(control_any_focused_app=True)
    direct = rules.interpret(
        f"{verb} Test Option.", language="en", context=context, pending=None
    )
    assert isinstance(direct, ReadyCommand)
    assert (
        direct.intent.target == "Test Option" and direct.intent.control_state is state
    )
    interpreter = _interpreter(
        tmp_path,
        FakeModel(_visible_ready("Test Option", "1", state)),
        visible_options=(
            VisibleOption("1", "Test Option", "accessibility", "check box", False),
        ),
        allow_visible_control=True,
    )
    result = interpreter.interpret(
        f"Could you {verb} Test Option?", language="en", context=context, pending=None
    )
    assert isinstance(result, ReadyCommand)
    assert (
        result.intent.target == "Test Option" and result.intent.control_state is state
    )


@pytest.mark.parametrize(
    "text",
    [
        "Do not click Test Button",
        'Say "click Test Button"',
        'What does "click Test Button" mean?',
    ],
)
def test_control_name_never_overrides_non_action_role(
    tmp_path: Path, text: str
) -> None:
    interpreter = _interpreter(
        tmp_path,
        FakeModel(_visible_ready("Test Button", "1")),
        visible_options=(VisibleOption("1", "Test Button", "accessibility", "button"),),
        allow_visible_control=True,
    )
    assert not isinstance(
        interpreter.interpret(
            text,
            language="en",
            context=CommandContext(observed_scroll_app="example.desktop"),
            pending=None,
        ),
        ReadyCommand,
    )
