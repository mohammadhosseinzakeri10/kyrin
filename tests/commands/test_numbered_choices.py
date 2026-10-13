"""Numbered choices never authorize an unlisted or stale action."""

from pathlib import Path

import pytest

from kyrin.commands.choice_numbers import choice_index
from kyrin.commands.coordinator import CommandCoordinator
from kyrin.commands.demo_interpreter import DemoCommandInterpreter
from kyrin.commands.models import (
    CommandIntent,
    CommandKind,
    CommandResolution,
    ResponseKind,
    ResponseRequest,
)
from kyrin.desktop.platforms.xdg import XdgDesktopAppCatalog
from kyrin.desktop.spoken_app_names import CatalogSpokenAppResolver
from kyrin.desktop.window_presence import WindowPresence
from kyrin.responses.presenter import ResponsePresenter
from kyrin.stt.transcript import TranscriptStatus, TranscriptUpdate


@pytest.mark.parametrize(
    ("speech", "index"),
    [
        ("1", 0),
        ("۱", 0),
        ("one", 0),
        ("number one", 0),
        ("option two", 1),
        ("شماره دو", 1),
        ("گزینه ۲", 1),
        ("یک", 0),
        ("number three", None),
        ("one or two", None),
        ("won", None),
        ("twenty-two", None),
        ("number twenty two", None),
    ],
)
def test_menu_number_requires_a_complete_in_range_answer(
    speech: str, index: int | None
) -> None:
    assert choice_index(speech, 2) == index


@pytest.mark.parametrize(("speech", "number"), (
    ("number twenty-two", 22),
    ("twenty two", 22),
    ("شماره بیست و دو", 22),
    ("۲۲", 22),
    ("forty", 40),
    ("نود و نه", 99),
))
def test_larger_picker_numbers_accept_digits_and_spoken_words(
    speech: str, number: int
) -> None:
    assert choice_index(speech, 99) == number - 1


class Presence:
    def __init__(self, state: WindowPresence) -> None:
        self.state = state
        self.calls = 0

    def observe(self, app_id: str) -> WindowPresence:
        assert app_id == "telegram"
        self.calls += 1
        return self.state


def _coordinator(tmp_path: Path, presence: WindowPresence) -> CommandCoordinator:
    directory = tmp_path / "applications"
    directory.mkdir()
    (directory / "telegram.desktop").write_text(
        "[Desktop Entry]\nType=Application\nName=Telegram\n", encoding="utf-8"
    )
    names = CatalogSpokenAppResolver(
        XdgDesktopAppCatalog((tmp_path,)),
        {"telegram.desktop": "telegram"},
        {"telegram": ("تلگرام",)},
    )
    return CommandCoordinator(
        DemoCommandInterpreter(
            names,
            allowed_window_apps=frozenset({"telegram"}),
            allowed_close_apps=frozenset({"telegram"}),
            window_presence=Presence(presence),
        )
    )


def _final(segment: int, text: str) -> TranscriptUpdate:
    return TranscriptUpdate(segment, text, TranscriptStatus.FINAL, "en")


def test_bare_app_name_offers_current_window_actions_and_confirms_close(
    tmp_path: Path,
) -> None:
    coordinator = _coordinator(tmp_path, WindowPresence.OPEN)
    question = coordinator.observe(_final(0, "Telegram"))
    assert question[0] == CommandResolution(0, None, language="en")
    assert isinstance(question[1], ResponseRequest)
    assert question[1].kind is ResponseKind.CHOOSE_OPERATION
    assert question[1].operation_candidates == (
        CommandKind.OPEN_APP,
        CommandKind.MINIMIZE_APP,
        CommandKind.CLOSE_APP_WINDOW,
    )
    assert "3. Close" in ResponsePresenter("en").present(question[1]).text
    close = coordinator.observe(_final(1, "number three"))
    assert close[0] == CommandResolution(1, None, language="en")
    assert isinstance(close[1], ResponseRequest)
    assert close[1].kind is ResponseKind.CONFIRM_ACTION
    assert coordinator.observe(_final(2, "no")) == (
        CommandResolution(2, None, language="en"),
    )
    assert coordinator.observe(_final(3, "yes"))[0] == CommandResolution(
        3, None, language="en"
    )


def test_bare_app_name_accepts_yes_for_open_and_no_for_cancel(tmp_path: Path) -> None:
    coordinator = _coordinator(tmp_path, WindowPresence.OPEN)
    prompt = coordinator.observe(_final(0, "Telegram"))
    assert "yes to open" in ResponsePresenter("en").present(prompt[1]).text
    assert coordinator.observe(_final(1, "yes")) == (
        CommandResolution(
            1, CommandIntent(CommandKind.OPEN_APP, "telegram"), language="en"
        ),
    )
    coordinator.observe(_final(2, "Telegram"))
    assert coordinator.observe(_final(3, "no")) == (
        CommandResolution(3, None, language="en"),
    )
    assert coordinator.observe(_final(4, "yes"))[0].intent is None


def test_bare_app_name_when_closed_asks_yes_or_no(tmp_path: Path) -> None:
    coordinator = _coordinator(tmp_path, WindowPresence.CLOSED)
    prompt = coordinator.observe(_final(0, "Telegram"))
    assert ResponsePresenter("en").present(prompt[1]).text == (
        "Open Telegram? Say yes or no."
    )
    assert coordinator.observe(_final(1, "yes"))[0].intent == CommandIntent(
        CommandKind.OPEN_APP, "telegram"
    )


def test_registered_persian_open_synonym_uses_same_open_action(tmp_path: Path) -> None:
    coordinator = _coordinator(tmp_path, WindowPresence.CLOSED)
    assert coordinator.observe(_final(0, "تلگرام را اجرا کن"))[0].intent == (
        CommandIntent(CommandKind.OPEN_APP, "telegram")
    )


@pytest.mark.parametrize("phrase", (
    "Make Telegram smaller", "Please make Telegram smaller than now",
    "تلگرام را کوچک تر کن",
))
def test_ambiguous_smaller_request_asks_which_window_action(
    tmp_path: Path, phrase: str
) -> None:
    coordinator = _coordinator(tmp_path, WindowPresence.OPEN)
    prompt = coordinator.observe(_final(0, phrase))
    assert prompt[0].intent is None
    assert prompt[1].operation_candidates == (
        CommandKind.MINIMIZE_APP, CommandKind.UNMAXIMIZE_APP
    )
    assert coordinator.observe(_final(1, "yes"))[0].intent is None
    assert coordinator.observe(_final(2, "normal size")) == (
        CommandResolution(
            2,
            CommandIntent(CommandKind.UNMAXIMIZE_APP, "telegram"),
            language="en",
        ),
    )


def test_smaller_without_a_verified_target_does_not_change_any_window(
    tmp_path: Path,
) -> None:
    coordinator = _coordinator(tmp_path, WindowPresence.OPEN)
    assert coordinator.observe(_final(0, "make it smaller"))[0].intent is None


def test_bare_app_name_without_window_offers_only_open(tmp_path: Path) -> None:
    coordinator = _coordinator(tmp_path, WindowPresence.CLOSED)
    question = coordinator.observe(_final(0, "Telegram"))
    assert isinstance(question[1], ResponseRequest)
    assert question[1].operation_candidates == (CommandKind.OPEN_APP,)
    assert coordinator.observe(_final(1, "number two"))[0] == CommandResolution(
        1, None, language="en"
    )
    assert coordinator.observe(_final(2, "one")) == (
        CommandResolution(
            2, CommandIntent(CommandKind.OPEN_APP, "telegram"), language="en"
        ),
    )


def test_partial_app_name_does_not_probe_the_desktop(tmp_path: Path) -> None:
    directory = tmp_path / "applications"
    directory.mkdir()
    (directory / "telegram.desktop").write_text(
        "[Desktop Entry]\nType=Application\nName=Telegram\n", encoding="utf-8"
    )
    names = CatalogSpokenAppResolver(
        XdgDesktopAppCatalog((tmp_path,)), {"telegram.desktop": "telegram"}
    )
    presence = Presence(WindowPresence.OPEN)
    coordinator = CommandCoordinator(
        DemoCommandInterpreter(names, window_presence=presence)
    )
    assert coordinator.observe(
        TranscriptUpdate(0, "Telegram", TranscriptStatus.PARTIAL, "en")
    ) == ()
    assert presence.calls == 0
    coordinator.observe(_final(0, "Telegram"))
    assert presence.calls == 1


def test_phonetic_app_proposal_needs_target_then_operation(tmp_path: Path) -> None:
    directory = tmp_path / "applications"
    directory.mkdir()
    (directory / "v2rayn.desktop").write_text(
        "[Desktop Entry]\nType=Application\nName=V2RayN\n", encoding="utf-8"
    )
    names = CatalogSpokenAppResolver(
        XdgDesktopAppCatalog((tmp_path,)), {"v2rayn.desktop": "v2rayn"}
    )
    assert names.resolve("VTorain").candidates == ()
    assert names.suggest("VTorain").candidates[0].app_id == "v2rayn"
    coordinator = CommandCoordinator(DemoCommandInterpreter(names))
    first = coordinator.observe(_final(0, "VTorain"))
    assert isinstance(first[1], ResponseRequest)
    assert first[1].kind is ResponseKind.CONFIRM_APP
    second = coordinator.observe(_final(1, "yes"))
    assert second[0] == CommandResolution(1, None, language="en")
    assert isinstance(second[1], ResponseRequest)
    assert second[1].kind is ResponseKind.CHOOSE_OPERATION
    assert coordinator.observe(_final(2, "one")) == (
        CommandResolution(
            2, CommandIntent(CommandKind.OPEN_APP, "v2rayn"), language="en"
        ),
    )


@pytest.mark.parametrize("phrase", ("Close VTorrain", "Close V2 Rain", "Exit V2 Rain"))
def test_uncertain_close_target_requires_app_and_action_confirmation(
    tmp_path: Path, phrase: str
) -> None:
    directory = tmp_path / "applications"
    directory.mkdir()
    (directory / "v2rayn.desktop").write_text(
        "[Desktop Entry]\nType=Application\nName=V2RayN\n", encoding="utf-8"
    )
    names = CatalogSpokenAppResolver(
        XdgDesktopAppCatalog((tmp_path,)), {"v2rayn.desktop": "v2rayn"}
    )
    coordinator = CommandCoordinator(DemoCommandInterpreter(names))
    first = coordinator.observe(_final(0, phrase))
    assert first[0] == CommandResolution(0, None, language="en")
    assert isinstance(first[1], ResponseRequest)
    assert first[1].kind is ResponseKind.CONFIRM_APP
    second = coordinator.observe(_final(1, "yes"))
    assert second[0] == CommandResolution(1, None, language="en")
    assert isinstance(second[1], ResponseRequest)
    assert second[1].kind is ResponseKind.CONFIRM_ACTION
    assert coordinator.observe(_final(2, "yes")) == (
        CommandResolution(
            2, CommandIntent(CommandKind.CLOSE_APP_WINDOW, "v2rayn"), language="en"
        ),
    )


def test_rejected_close_suggestion_never_closes_app(tmp_path: Path) -> None:
    directory = tmp_path / "applications"
    directory.mkdir()
    (directory / "v2rayn.desktop").write_text(
        "[Desktop Entry]\nType=Application\nName=V2RayN\n", encoding="utf-8"
    )
    names = CatalogSpokenAppResolver(
        XdgDesktopAppCatalog((tmp_path,)), {"v2rayn.desktop": "v2rayn"}
    )
    coordinator = CommandCoordinator(DemoCommandInterpreter(names))
    coordinator.observe(_final(0, "Close V2 Rain"))
    assert coordinator.observe(_final(1, "no")) == (
        CommandResolution(1, None, language="en"),
    )
    assert coordinator.observe(_final(2, "yes"))[0] == CommandResolution(
        2, None, language="en"
    )
