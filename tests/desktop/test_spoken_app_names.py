"""A registered name can suggest an app but cannot bypass confirmation."""

from pathlib import Path

from kyrin.actions.gate import ActionGate, ActionPolicy
from kyrin.actions.models import ActionRequest
from kyrin.commands.coordinator import CommandCoordinator
from kyrin.commands.demo_interpreter import DemoCommandInterpreter
from kyrin.commands.models import (
    CommandCandidateUpdate,
    CommandIntent,
    CommandKind,
    CommandResolution,
    ResponseKind,
    ResponseRequest,
)
from kyrin.desktop.platforms.xdg import XdgDesktopAppCatalog
from kyrin.desktop.spoken_app_names import CatalogSpokenAppResolver
from kyrin.responses.presenter import ResponsePresenter
from kyrin.stt.transcript import TranscriptStatus, TranscriptUpdate


def _entry(root: Path, desktop_id: str, name: str) -> None:
    path = root / "applications" / desktop_id
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"[Desktop Entry]\nType=Application\nName={name}\n",
        encoding="utf-8",
    )


def _final(segment: int, text: str) -> TranscriptUpdate:
    return TranscriptUpdate(segment, text, TranscriptStatus.FINAL, "en")


def test_catalog_alias_and_approximate_name_require_different_decisions(
    tmp_path: Path,
) -> None:
    _entry(tmp_path, "whatsapp.desktop", "WhatsApp")
    _entry(tmp_path, "telegram.desktop", "Telegram")
    _entry(tmp_path, "unbound.desktop", "Unbound")
    resolver = CatalogSpokenAppResolver(
        XdgDesktopAppCatalog((tmp_path,)),
        {"whatsapp.desktop": "whatsapp", "telegram.desktop": "telegram"},
        {"whatsapp": ("what's up",)},
    )
    assert resolver.resolve("what's up").candidates[0].app_id == "whatsapp"
    assert resolver.resolve("whatsapp").exact
    assert resolver.resolve("WhatsAp").exact is False
    assert resolver.resolve("Unbound").candidates == ()
    assert resolver.resolve("filler drum").candidates == ()

    coordinator = CommandCoordinator(DemoCommandInterpreter(resolver))
    gate = ActionGate(ActionPolicy(allowed_apps=frozenset({"whatsapp"})))
    direct = coordinator.observe(_final(0, "Go to WhatsApp"))
    assert direct == (
        CommandResolution(
            0, CommandIntent(CommandKind.OPEN_APP, "whatsapp"), language="en"
        ),
    )
    assert isinstance(gate.observe(direct[0]), ActionRequest)

    coordinator = CommandCoordinator(DemoCommandInterpreter(resolver))
    gate = ActionGate(ActionPolicy(allowed_apps=frozenset({"whatsapp"})))
    alias = coordinator.observe(_final(0, "Go to what's up"))
    assert alias == (
        CommandResolution(
            0, CommandIntent(CommandKind.OPEN_APP, "whatsapp"), language="en"
        ),
    )
    assert isinstance(gate.observe(alias[0]), ActionRequest)

    proposed = coordinator.observe(_final(1, "Go to WhatsAp"))
    assert proposed[0] == CommandResolution(1, None, language="en")
    assert isinstance(proposed[1], ResponseRequest)
    assert proposed[1].kind is ResponseKind.CONFIRM_APP
    assert ResponsePresenter("en").present(proposed[1]).text == (
        "Did you mean the WhatsApp app?"
    )
    assert gate.observe(proposed[0]) is None
    accepted = coordinator.observe(_final(2, "yes"))
    assert accepted == (
        CommandResolution(
            2, CommandIntent(CommandKind.OPEN_APP, "whatsapp"), language="en"
        ),
    )


def test_rejected_suggestion_never_becomes_an_action(tmp_path: Path) -> None:
    _entry(tmp_path, "whatsapp.desktop", "WhatsApp")
    resolver = CatalogSpokenAppResolver(
        XdgDesktopAppCatalog((tmp_path,)), {"whatsapp.desktop": "whatsapp"}
    )
    coordinator = CommandCoordinator(DemoCommandInterpreter(resolver))
    coordinator.observe(_final(0, "open WhatsAp"))
    assert coordinator.pending_clarification is not None
    assert coordinator.observe(_final(1, "no")) == (
        CommandResolution(1, None, language="en"),
    )
    assert coordinator.pending_clarification is None
    assert coordinator.observe(_final(2, "yes")) == (
        CommandResolution(2, None, language="en"),
    )


def test_partial_match_and_negation_never_authorize_an_action(tmp_path: Path) -> None:
    _entry(tmp_path, "telegram.desktop", "Telegram")
    resolver = CatalogSpokenAppResolver(
        XdgDesktopAppCatalog((tmp_path,)), {"telegram.desktop": "telegram"}
    )
    coordinator = CommandCoordinator(DemoCommandInterpreter(resolver))
    gate = ActionGate(ActionPolicy(allowed_apps=frozenset({"telegram"})))
    partial = coordinator.observe(
        TranscriptUpdate(0, "open Telegram", TranscriptStatus.PARTIAL, "en")
    )
    assert partial == (
        CommandCandidateUpdate(0, CommandIntent(CommandKind.OPEN_APP, "telegram")),
    )
    assert gate.observe(partial[0]) is None
    final = coordinator.observe(_final(0, "do not open Telegram"))
    assert final == (CommandResolution(0, None, language="en"),)
    assert gate.observe(final[-1]) is None


def test_same_label_for_distinct_apps_asks_for_choice(tmp_path: Path) -> None:
    _entry(tmp_path, "first.desktop", "Google Chrome")
    _entry(tmp_path, "second.desktop", "Google Chrome")
    resolver = CatalogSpokenAppResolver(
        XdgDesktopAppCatalog((tmp_path,)),
        {"first.desktop": "chrome_a", "second.desktop": "chrome_b"},
        {"chrome_a": ("Chrome Work",)},
    )
    coordinator = CommandCoordinator(DemoCommandInterpreter(resolver))
    result = coordinator.observe(_final(0, "open Google Chrome"))
    assert result[0] == CommandResolution(0, None, language="en")
    assert isinstance(result[1], ResponseRequest)
    assert result[1].kind is ResponseKind.CHOOSE_APP
    # Saying the same ambiguous label again must not select either application.
    second = coordinator.observe(_final(1, "Google Chrome"))
    assert second[0] == CommandResolution(1, None, language="en")
    assert isinstance(second[1], ResponseRequest)
    assert second[1].kind is ResponseKind.CHOOSE_APP
    assert ResponsePresenter("en").present(second[1]).text == (
        "Multiple apps are named Google Chrome. Please use a different name."
    )
    selected = coordinator.observe(_final(2, "Chrome Work"))
    assert selected == (
        CommandResolution(
            2, CommandIntent(CommandKind.OPEN_APP, "chrome_a"), language="en"
        ),
    )


def test_refresh_replaces_stale_catalog_snapshot(tmp_path: Path) -> None:
    _entry(tmp_path, "chat.desktop", "Chat One")
    resolver = CatalogSpokenAppResolver(
        XdgDesktopAppCatalog((tmp_path,)), {"chat.desktop": "chat"}
    )
    assert resolver.resolve("Chat One").exact
    _entry(tmp_path, "chat.desktop", "Chat Two")
    resolver.refresh()
    assert resolver.resolve("Chat One").candidates == ()
    assert resolver.resolve("Chat Two").exact
