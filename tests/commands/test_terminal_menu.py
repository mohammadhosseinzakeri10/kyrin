"""Terminal choices depend on the current GNOME window count."""

from pathlib import Path

from kyrin.commands.coordinator import CommandCoordinator
from kyrin.commands.demo_interpreter import DemoCommandInterpreter
from kyrin.commands.models import (
    CommandIntent,
    CommandKind,
    CommandResolution,
    ResponseChannel,
    ResponseKind,
    ResponseRequest,
)
from kyrin.desktop.platforms.xdg import XdgDesktopAppCatalog
from kyrin.desktop.spoken_app_names import CatalogSpokenAppResolver
from kyrin.desktop.window_presence import WindowPresence
from kyrin.stt.transcript import TranscriptStatus, TranscriptUpdate


class Presence:
    def __init__(self, count: int | None) -> None:
        self.windows = count
        self.calls = 0

    def count(self, app_id: str) -> int | None:
        assert app_id == "terminal"
        self.calls += 1
        return self.windows

    def observe(self, app_id: str) -> WindowPresence:
        return WindowPresence.UNKNOWN


def _final(segment: int, text: str) -> TranscriptUpdate:
    return TranscriptUpdate(segment, text, TranscriptStatus.FINAL, "en")


def _session(tmp_path: Path, count: int | None) -> tuple[CommandCoordinator, Presence]:
    directory = tmp_path / "applications"
    directory.mkdir()
    (directory / "org.gnome.Ptyxis.desktop").write_text(
        "[Desktop Entry]\nType=Application\nName=Terminal\n", encoding="utf-8"
    )
    names = CatalogSpokenAppResolver(
        XdgDesktopAppCatalog((tmp_path,)),
        {"org.gnome.Ptyxis.desktop": "terminal"},
    )
    presence = Presence(count)
    return CommandCoordinator(
        DemoCommandInterpreter(
            names,
            terminal_app_id="terminal",
            window_presence=presence,
            allowed_window_apps=frozenset({"terminal"}),
        )
    ), presence


def test_no_terminal_window_launches_once(tmp_path: Path) -> None:
    coordinator, presence = _session(tmp_path, 0)
    assert coordinator.observe(_final(0, "Open Terminal")) == (
        CommandResolution(
            0, CommandIntent(CommandKind.OPEN_APP, "terminal"), language="en"
        ),
    )
    assert presence.calls == 1


def test_one_terminal_window_asks_before_opening_another(tmp_path: Path) -> None:
    coordinator, _ = _session(tmp_path, 1)
    first = coordinator.observe(_final(0, "Open Terminal"))
    assert first[0] == CommandResolution(0, None, language="en")
    assert isinstance(first[1], ResponseRequest)
    assert first[1].operation_candidates == (
        CommandKind.OPEN_APP,
        CommandKind.NEW_APP_WINDOW,
        CommandKind.NEW_APP_TAB,
        CommandKind.APP_PREFERENCES,
    )
    assert coordinator.observe(_final(1, "number three")) == (
        CommandResolution(
            1, CommandIntent(CommandKind.NEW_APP_TAB, "terminal"), language="en"
        ),
    )


def test_multiple_terminal_windows_offer_overview_without_ambiguous_tab(
    tmp_path: Path,
) -> None:
    coordinator, _ = _session(tmp_path, 3)
    first = coordinator.observe(_final(0, "Open Terminal"))
    assert isinstance(first[1], ResponseRequest)
    assert first[1].operation_candidates == (
        CommandKind.SHOW_APP_WINDOWS,
        CommandKind.NEW_APP_WINDOW,
        CommandKind.APP_PREFERENCES,
    )
    assert coordinator.observe(_final(1, "one")) == (
        CommandResolution(
            1, CommandIntent(CommandKind.SHOW_APP_WINDOWS, "terminal"), language="en"
        ),
        ResponseRequest(
            1,
            ResponseKind.CHOOSE_WINDOW,
            ResponseChannel.TEXT_ONLY,
            target="Terminal",
            window_count=3,
            language="en",
        ),
    )
    assert coordinator.observe(_final(2, "number two")) == (
        CommandResolution(
            2,
            CommandIntent(CommandKind.SELECT_APP_WINDOW, "terminal", window_index=2),
            language="en",
        ),
    )


def test_terminal_window_picker_can_be_cancelled_by_voice(tmp_path: Path) -> None:
    coordinator, _ = _session(tmp_path, 2)
    coordinator.observe(_final(0, "Open Terminal"))
    coordinator.observe(_final(1, "one"))
    assert coordinator.observe(_final(2, "cancel")) == (
        CommandResolution(
            2, CommandIntent(CommandKind.HIDE_APP_WINDOWS, "terminal"), language="en"
        ),
    )


def test_terminal_window_can_be_closed_by_number_after_confirmation(
    tmp_path: Path,
) -> None:
    coordinator, _ = _session(tmp_path, 3)
    coordinator.observe(_final(0, "Open Terminal"))
    coordinator.observe(_final(1, "one"))
    asked = coordinator.observe(_final(2, "quit number three"))
    assert asked[0].intent is None
    assert asked[1].kind is ResponseKind.CONFIRM_NUMBERED_CLOSE
    assert asked[1].window_index == 3
    assert coordinator.observe(_final(3, "yes")) == (
        CommandResolution(3, CommandIntent(
            CommandKind.CLOSE_SHOWN_WINDOW, "terminal", window_index=3
        ), language="en"),
    )


def test_unknown_window_count_never_assumes_a_new_window_is_needed(
    tmp_path: Path,
) -> None:
    coordinator, _ = _session(tmp_path, None)
    first = coordinator.observe(_final(0, "Open Terminal"))
    assert isinstance(first[1], ResponseRequest)
    assert first[1].operation_candidates == (CommandKind.OPEN_APP,)


def test_close_terminal_requires_a_separate_confirmation(tmp_path: Path) -> None:
    coordinator, _ = _session(tmp_path, 1)
    first = coordinator.observe(_final(0, "Close Terminal"))
    assert first[0] == CommandResolution(0, None, language="en")
    assert isinstance(first[1], ResponseRequest)
    assert coordinator.observe(_final(1, "no")) == (
        CommandResolution(1, None, language="en"),
    )
    second = coordinator.observe(_final(2, "Close Terminal"))
    assert isinstance(second[1], ResponseRequest)
    assert coordinator.observe(_final(3, "yes")) == (
        CommandResolution(
            3,
            CommandIntent(CommandKind.CLOSE_APP_WINDOW, "terminal"),
            language="en",
        ),
    )
