"""Ptyxis actions use fixed arguments and only the bound application."""

import json
import subprocess
from pathlib import Path

from kyrin.actions.models import ActionKey, ActionOutcome, ActionRequest
from kyrin.actions.platforms import ptyxis
from kyrin.actions.platforms.ptyxis import PtyxisActionExecutor
from kyrin.commands.models import CommandIntent, CommandKind
from kyrin.desktop.window_presence import WindowPresence


class Fallback:
    def execute(self, request: ActionRequest):
        raise AssertionError(f"unexpected fallback: {request.intent.kind}")


class Presence:
    def __init__(self, count: int) -> None:
        self.windows = count

    def count(self, app_id: str) -> int:
        return self.windows

    def observe(self, app_id: str) -> WindowPresence:
        return WindowPresence.OPEN


def test_fixed_new_window_command(monkeypatch, tmp_path: Path) -> None:
    entry = tmp_path / "org.gnome.Ptyxis.desktop"
    entry.write_text("[Desktop Entry]\n", encoding="utf-8")
    calls: list[list[str]] = []

    def run(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(args)
        return subprocess.CompletedProcess(args, 0, "", "")

    monkeypatch.setattr(ptyxis.subprocess, "run", run)
    executor = PtyxisActionExecutor(Fallback(), "terminal", entry)
    result = executor.execute(
        ActionRequest(
            ActionKey(0, 0), CommandIntent(CommandKind.NEW_APP_WINDOW, "terminal")
        )
    )
    assert result.outcome is ActionOutcome.LAUNCH_ACCEPTED
    assert calls == [["ptyxis", "--new-window"]]


def test_unbound_app_never_reaches_terminal_command(
    monkeypatch, tmp_path: Path
) -> None:
    entry = tmp_path / "org.gnome.Ptyxis.desktop"
    entry.write_text("[Desktop Entry]\n", encoding="utf-8")

    def run(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("must not invoke Ptyxis")

    monkeypatch.setattr(ptyxis.subprocess, "run", run)
    executor = PtyxisActionExecutor(Fallback(), "terminal", entry)
    result = executor.execute(
        ActionRequest(
            ActionKey(0, 0), CommandIntent(CommandKind.NEW_APP_TAB, "other")
        )
    )
    assert result.outcome is ActionOutcome.FAILED


def test_new_tab_is_rejected_if_window_count_changed(
    monkeypatch, tmp_path: Path
) -> None:
    entry = tmp_path / "org.gnome.Ptyxis.desktop"
    entry.write_text("[Desktop Entry]\n", encoding="utf-8")

    def run(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("must not open a tab in an ambiguous window")

    monkeypatch.setattr(ptyxis.subprocess, "run", run)
    executor = PtyxisActionExecutor(Fallback(), "terminal", entry, Presence(2))
    result = executor.execute(
        ActionRequest(
            ActionKey(0, 0), CommandIntent(CommandKind.NEW_APP_TAB, "terminal")
        )
    )
    assert result.outcome is ActionOutcome.UNKNOWN
    assert result.error_code == "window_state_changed"


def test_numbered_picker_uses_only_bound_terminal_and_reports_stale(
    monkeypatch, tmp_path: Path
) -> None:
    entry = tmp_path / "org.gnome.Ptyxis.desktop"
    entry.write_text("[Desktop Entry]\n", encoding="utf-8")
    calls: list[list[str]] = []
    replies = iter(("requested", "stale"))

    def run(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(args)
        return subprocess.CompletedProcess(
            args, 0, json.dumps({"type": "s", "data": [next(replies)]}), ""
        )

    monkeypatch.setattr(ptyxis.subprocess, "run", run)
    executor = PtyxisActionExecutor(Fallback(), "terminal", entry, Presence(3))
    shown = executor.execute(
        ActionRequest(
            ActionKey(0, 0), CommandIntent(CommandKind.SHOW_APP_WINDOWS, "terminal")
        )
    )
    stale = executor.execute(
        ActionRequest(
            ActionKey(0, 1),
            CommandIntent(CommandKind.SELECT_APP_WINDOW, "terminal", window_index=2),
        )
    )
    assert shown.outcome is ActionOutcome.LAUNCH_ACCEPTED
    assert stale.outcome is ActionOutcome.UNKNOWN
    assert stale.error_code == "window_state_changed"
    assert calls[0][-2:] == ["s", "org.gnome.Ptyxis.desktop"]
    assert calls[1][-3:] == ["su", "org.gnome.Ptyxis.desktop", "2"]


def test_numbered_terminal_close_requires_displayed_picker(
    monkeypatch, tmp_path: Path
) -> None:
    entry = tmp_path / "org.gnome.Ptyxis.desktop"
    entry.write_text("[Desktop Entry]\n", encoding="utf-8")
    calls: list[list[str]] = []

    def run(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(args)
        return subprocess.CompletedProcess(
            args, 0, json.dumps({"data": ["requested"]}), ""
        )

    monkeypatch.setattr(ptyxis.subprocess, "run", run)
    executor = PtyxisActionExecutor(Fallback(), "terminal", entry, Presence(3))
    close = CommandIntent(CommandKind.CLOSE_SHOWN_WINDOW, "terminal", window_index=2)
    assert executor.execute(
        ActionRequest(ActionKey(0, 0), close)
    ).outcome is ActionOutcome.FAILED
    executor.execute(ActionRequest(
        ActionKey(0, 1), CommandIntent(CommandKind.SHOW_APP_WINDOWS, "terminal")
    ))
    assert executor.execute(
        ActionRequest(ActionKey(0, 2), close)
    ).outcome is ActionOutcome.LAUNCH_ACCEPTED
    assert calls[1][-3:] == ["su", "org.gnome.Ptyxis.desktop", "2"]
