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
    monkeypatch.setattr(helper, "KEYBOARD_TOKEN_PATH", token_path)
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


def test_search_types_name_without_enter(
    helper: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    keys: list[tuple[int, bool]] = []
    monkeypatch.setattr(
        helper, "_key", lambda _bus, _session, key, down: keys.append((key, down))
    )
    monkeypatch.setattr(helper, "sleep", lambda _seconds: None)
    helper._type_search_target(object(), "/session", "Ali")
    pressed = [key for key, down in keys if down]
    assert pressed == [helper.CONTROL, ord("f"), ord("A"), ord("l"), ord("i")]
    assert 0xFF0D not in pressed  # Return/Enter could send a message.


def test_pointer_click_requires_matching_window_geometry_and_position(
    helper: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    expected = ("org.telegram.desktop", 42)
    observations = iter(
        [
            (*expected, 100, 50, 1600, 900, 500, 300),
            (*expected, 100, 50, 1600, 900, 215, 282),
        ]
    )
    monkeypatch.setattr(helper, "_window_and_pointer", lambda: next(observations))
    monkeypatch.setattr(helper, "sleep", lambda _seconds: None)
    helper.GLib.Variant = lambda signature, value: (signature, value)
    calls: list[str] = []

    class Bus:
        def call_sync(self, _bus, _object, _interface, method, *_args):
            calls.append(method)

    helper.Gio.DBusCallFlags = type("Flags", (), {"NONE": 0})
    assert helper._click_verified_box(
        Bus(), "/session", expected, (70, 220, 90, 24, 1600, 900)
    )
    assert calls == [
        "NotifyPointerMotion",
        "NotifyPointerButton",
        "NotifyPointerButton",
    ]


def test_pointer_does_not_click_when_geometry_differs(
    helper: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    expected = ("org.telegram.desktop", 42)
    monkeypatch.setattr(
        helper,
        "_window_and_pointer",
        lambda: (*expected, 100, 50, 1500, 900, 500, 300),
    )

    class Bus:
        def call_sync(self, *_args):
            pytest.fail("pointer input must be blocked")

    assert not helper._click_verified_box(
        Bus(), "/session", expected, (70, 220, 90, 24, 1600, 900)
    )


def test_pointer_portal_grant_is_session_only(
    helper: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    expected = ("org.telegram.desktop", 42)
    monkeypatch.setattr(
        helper.sys,
        "argv",
        ["helper", expected[0], "42", "click", "70", "220", "90", "24", "1600", "900"],
    )
    monkeypatch.setattr(helper, "_focused_identity", lambda: expected)
    monkeypatch.setattr(helper, "_wait_for_expected_focus", lambda _identity: True)
    monkeypatch.setattr(helper, "_click_verified_box", lambda *_args: True)
    helper.Gio.bus_get_sync = lambda *_args: type(
        "Bus", (), {"call_sync": lambda *_args: None}
    )()
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
        return {"devices": 2}

    monkeypatch.setattr(helper, "_request", request)
    assert helper.main() == 0
    options = calls[1][1][1]
    assert options["types"] == ("u", 2)
    assert options["persist_mode"] == ("u", 0)
    assert "restore_token" not in options
