"""The command catalog repairs structure, not the name supplied by speech."""

import pytest

from kyrin.commands.chat_command_catalog import match_english_chat_command


@pytest.mark.parametrize(
    ("phrase", "scope", "name"),
    (
        ("open visibly chat my mother", "visible", "my mother"),
        ("openvisibly chat my mother", "visible", "my mother"),
        ("open visible chat my mother", "visible", "my mother"),
        ("open chat my mother", "search", "my mother"),
        ("open my mother chat", "search", "my mother"),
    ),
)
def test_chat_command_forms_keep_target_slot(
    phrase: str, scope: str, name: str
) -> None:
    match = match_english_chat_command(phrase)
    assert match is not None
    assert (match.scope, match.spoken_target) == (scope, name)


@pytest.mark.parametrize(
    "phrase",
    (
        "do not open visibly chat my mother",
        "open invisible chat my mother",
        "open visibly chat",
    ),
)
def test_chat_command_forms_reject_unreviewed_structure(phrase: str) -> None:
    assert match_english_chat_command(phrase) is None
