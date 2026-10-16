"""Smooth generic scrolling stays bounded and stops when focus changes."""

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

from kyrin.actions.platforms import desktop_scroll


@pytest.fixture
def helper(monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    gi = ModuleType("gi")
    repository = ModuleType("gi.repository")
    repository.Gio = ModuleType("Gio")
    repository.GLib = ModuleType("GLib")
    monkeypatch.setitem(sys.modules, "gi", gi)
    monkeypatch.setitem(sys.modules, "gi.repository", repository)
    path = Path(desktop_scroll.__file__).with_name("desktop_scroll_helper.py")
    spec = importlib.util.spec_from_file_location("desktop_scroll_helper_test", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.Gio.DBusCallFlags = type("Flags", (), {"NONE": 0})
    module.GLib.Variant = lambda signature, value: (signature, value)
    return module


def test_smooth_scroll_sends_small_axis_events(
    helper: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    expected = ("org.telegram.desktop", 42)
    frame = (*expected, 0, 0, 1000, 800, 150, 440)
    monkeypatch.setattr(helper, "_window_and_pointer", lambda: frame)
    monkeypatch.setattr(helper, "_focused_identity", lambda: expected)
    monkeypatch.setattr(helper, "sleep", lambda _seconds: None)
    calls: list[tuple[str, object]] = []

    class Bus:
        def call_sync(self, _bus, _object, _interface, method, payload, *_rest):
            calls.append((method, payload))

    assert helper._scroll(
        Bus(), "/session", expected,
        direction="down", steps=3, left_pane=True, smooth=True,
    )
    axes = [payload for method, payload in calls if method == "NotifyPointerAxis"]
    assert len(axes) == 12
    assert all(payload[1][3] == 8.0 for payload in axes)
    assert axes[-1][1][1]["finish"] == ("b", True)
    assert not any(method == "NotifyPointerAxisDiscrete" for method, _ in calls)


def test_smooth_scroll_stops_if_focus_changes(
    helper: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    expected = ("org.telegram.desktop", 42)
    frame = (*expected, 0, 0, 1000, 800, 150, 440)
    monkeypatch.setattr(helper, "_window_and_pointer", lambda: frame)
    seen = 0

    def focus() -> tuple[str, int]:
        nonlocal seen
        seen += 1
        return expected if seen < 4 else ("other.desktop", 9)

    monkeypatch.setattr(helper, "_focused_identity", focus)
    monkeypatch.setattr(helper, "sleep", lambda _seconds: None)
    calls: list[str] = []

    class Bus:
        def call_sync(self, _bus, _object, _interface, method, *_rest):
            calls.append(method)

    assert not helper._scroll(
        Bus(), "/session", expected,
        direction="down", steps=3, left_pane=True, smooth=True,
    )
    assert calls.count("NotifyPointerAxis") == 2
