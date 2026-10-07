"""A registered app whose name reads like a chat command needs a choice."""

from pathlib import Path

import pytest

from kyrin.actions.gate import ActionGate, ActionPolicy
from kyrin.actions.models import ActionRequest
from kyrin.commands.coordinator import CommandCoordinator
from kyrin.commands.demo_interpreter import DemoCommandInterpreter
from kyrin.commands.models import (
    CommandIntent,
    CommandKind,
    CommandResolution,
    PendingIntentClarification,
    ResponseKind,
    ResponseRequest,
)
from kyrin.desktop.platforms.xdg import XdgDesktopAppCatalog
from kyrin.desktop.spoken_app_names import CatalogSpokenAppResolver
from kyrin.responses.presenter import ResponsePresenter
from kyrin.stt.transcript import TranscriptStatus, TranscriptUpdate


def _coordinator(tmp_path: Path) -> CommandCoordinator:
    app_dir = tmp_path / "applications"
    app_dir.mkdir()
    (app_dir / "chat-one.desktop").write_text(
        "[Desktop Entry]\nType=Application\nName=Chat One\n", encoding="utf-8"
    )
    (app_dir / "telegram.desktop").write_text(
        "[Desktop Entry]\nType=Application\nName=Telegram\n", encoding="utf-8"
    )
    resolver = CatalogSpokenAppResolver(
        XdgDesktopAppCatalog((tmp_path,)),
        {"chat-one.desktop": "chat_one", "telegram.desktop": "telegram"},
    )
    return CommandCoordinator(DemoCommandInterpreter(resolver))


def _final(segment: int, text: str) -> TranscriptUpdate:
    return TranscriptUpdate(segment, text, TranscriptStatus.FINAL, "en")


def test_ambiguous_app_or_chat_requires_explicit_choice(tmp_path: Path) -> None:
    coordinator = _coordinator(tmp_path)
    gate = ActionGate(
        ActionPolicy(
            allowed_apps=frozenset({"chat_one"}),
            supported_kinds=frozenset({CommandKind.OPEN_APP}),
        )
    )

    first = coordinator.observe(_final(0, "Open Chat One"))
    assert first[0] == CommandResolution(0, None, language="en")
    assert isinstance(first[1], ResponseRequest)
    assert first[1].kind is ResponseKind.CHOOSE_APP_OR_CHAT
    assert isinstance(coordinator.pending_clarification, PendingIntentClarification)
    assert "app or a chat" in ResponsePresenter("en").present(first[1]).text
    assert gate.observe(first[0]) is None

    unclear = coordinator.observe(_final(1, "yes"))
    assert unclear[0] == CommandResolution(1, None, language="en")
    assert isinstance(unclear[1], ResponseRequest)
    assert unclear[1].kind is ResponseKind.CHOOSE_APP_OR_CHAT
    assert gate.observe(unclear[0]) is None

    selected = coordinator.observe(_final(2, "app"))
    assert selected == (
        CommandResolution(
            2,
            CommandIntent(CommandKind.OPEN_APP, "chat_one"),
            language="en",
        ),
    )
    assert isinstance(gate.observe(selected[0]), ActionRequest)


def test_chat_choice_uses_fresh_context_and_never_opens_app(tmp_path: Path) -> None:
    coordinator = _coordinator(tmp_path)
    coordinator.observe(_final(0, "Open Chat One"))
    chat = coordinator.observe(_final(1, "chat"), observed_active_app="telegram")

    assert len(chat) == 1
    assert isinstance(chat[0], CommandResolution)
    assert chat[0].intent is not None
    assert chat[0].intent.kind is CommandKind.OPEN_CHAT
    assert chat[0].intent.target == "one"
    assert chat[0].intent.app == "telegram"


def test_near_app_name_that_reads_as_chat_also_asks(tmp_path: Path) -> None:
    coordinator = _coordinator(tmp_path)
    result = coordinator.observe(_final(0, "Open Chat On"))
    assert result[0] == CommandResolution(0, None, language="en")
    assert isinstance(result[1], ResponseRequest)
    assert result[1].kind is ResponseKind.CHOOSE_APP_OR_CHAT


def test_persian_app_and_chat_name_also_requires_a_choice(tmp_path: Path) -> None:
    app_dir = tmp_path / "applications"
    app_dir.mkdir()
    (app_dir / "ali-chat.desktop").write_text(
        "[Desktop Entry]\nType=Application\nName=چت علی\n", encoding="utf-8"
    )
    resolver = CatalogSpokenAppResolver(
        XdgDesktopAppCatalog((tmp_path,)), {"ali-chat.desktop": "ali_chat"}
    )
    coordinator = CommandCoordinator(DemoCommandInterpreter(resolver))
    first = coordinator.observe(
        TranscriptUpdate(0, "چت علی را باز کن", TranscriptStatus.FINAL, "fa")
    )
    assert first[0] == CommandResolution(0, None, language="fa")
    assert isinstance(first[1], ResponseRequest)
    assert first[1].kind is ResponseKind.CHOOSE_APP_OR_CHAT
    assert "برنامه" in ResponsePresenter("fa").present(first[1]).text
    selected = coordinator.observe(
        TranscriptUpdate(1, "برنامه", TranscriptStatus.FINAL, "fa")
    )
    assert selected == (
        CommandResolution(
            1, CommandIntent(CommandKind.OPEN_APP, "ali_chat"), language="fa"
        ),
    )


def test_partial_then_negated_final_never_executes(tmp_path: Path) -> None:
    coordinator = _coordinator(tmp_path)
    partial = coordinator.observe(
        TranscriptUpdate(0, "Open Chat One", TranscriptStatus.PARTIAL, "en")
    )
    assert partial == ()
    final = coordinator.observe(_final(0, "Do not open Chat One"))
    assert final == (CommandResolution(0, None, language="en"),)
    assert coordinator.pending_clarification is None


@pytest.mark.parametrize(
    "phrase",
    (
        "Open Chat One and open Telegram",
        "Open Telegram and open Chat One",
        "Open Telegram and open Chat On",
    ),
)
def test_ambiguous_name_in_plan_blocks_whole_plan(tmp_path: Path, phrase: str) -> None:
    coordinator = _coordinator(tmp_path)
    result = coordinator.observe(_final(0, phrase))
    assert result[0] == CommandResolution(0, None, language="en")
    assert isinstance(result[1], ResponseRequest)
    assert result[1].kind is ResponseKind.REPEAT_COMMAND
