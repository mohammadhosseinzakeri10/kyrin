"""The keyboard portal waits for Telegram focus without a fixed ten-second delay."""

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

from kyrin.actions.platforms import telegram
from kyrin.app.permission_token import read_opaque_token, save_opaque_token


@pytest.fixture
def helper(monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    gi = ModuleType("gi")
    repository = ModuleType("gi.repository")
    repository.Gio = ModuleType("Gio")
    repository.GLib = ModuleType("GLib")
    monkeypatch.setitem(sys.modules, "gi", gi)
    monkeypatch.setitem(sys.modules, "gi.repository", repository)
    path = Path(telegram.__file__).with_name("telegram_portal_helper.py")
    spec = importlib.util.spec_from_file_location("telegram_portal_helper_test", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(
    ("seen", "expected_result", "maximum_elapsed"),
    [
        (["telegram", "telegram"], True, 0.2),
        ([None, "other", "telegram", "telegram"], True, 0.6),
        (["telegram", "other", "telegram", "telegram"], True, 0.6),
        ([None], False, 10.0),
    ],
)
def test_waits_for_stable_focus_without_unconditional_delay(
    helper: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    seen: list[str | None],
    expected_result: bool,
    maximum_elapsed: float,
) -> None:
    expected = ("org.telegram.desktop.desktop", 42)
    elapsed = 0.0
    observations = iter(seen)

    def focus() -> tuple[str, int] | None:
        value = next(observations, seen[-1])
        return expected if value == "telegram" else ("other.desktop", 9)

    def sleep(seconds: float) -> None:
        nonlocal elapsed
        elapsed += seconds

    monkeypatch.setattr(helper, "_focused_identity", focus)
    monkeypatch.setattr(helper, "monotonic", lambda: elapsed)
    monkeypatch.setattr(helper, "sleep", sleep)

    assert helper._wait_for_expected_focus(expected) is expected_result
    assert elapsed <= maximum_elapsed


def test_portal_restores_and_rotates_keyboard_token(
    helper: ModuleType, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    token_path = tmp_path / "telegram-keyboard.token"
    save_opaque_token(token_path, "old-opaque-token")
    monkeypatch.setattr(helper, "TOKEN_PATH", token_path)
    monkeypatch.setattr(helper.sys, "argv", ["helper", "org.telegram.desktop", "42"])
    expected = ("org.telegram.desktop", 42)
    monkeypatch.setattr(helper, "_focused_identity", lambda: expected)
    monkeypatch.setattr(helper, "_wait_for_expected_focus", lambda _identity: True)
    monkeypatch.setattr(helper, "_key", lambda *_args: None)

    class Bus:
        def call_sync(self, *_args):
            return None

    bus = Bus()
    helper.Gio.bus_get_sync = lambda *_args: bus
    helper.Gio.BusType = type("BusType", (), {"SESSION": 0})
    helper.Gio.DBusCallFlags = type("Flags", (), {"NONE": 0})
    helper.GLib.Variant = lambda signature, value: (signature, value)
    calls: list[tuple[str, object]] = []

    def request(_connection, method, arguments, _timeout):
        calls.append((method, arguments))
        if method == "CreateSession":
            return {"session_handle": "/test/session"}
        if method == "SelectDevices":
            return {}
        return {"devices": 1, "restore_token": "next-opaque-token"}

    monkeypatch.setattr(helper, "_request", request)
    assert helper.main() == 0
    assert calls[1][0] == "SelectDevices"
    options = calls[1][1][1]
    assert options["persist_mode"] == ("u", 2)
    assert options["restore_token"] == ("s", "old-opaque-token")
    assert read_opaque_token(token_path) == "next-opaque-token"
