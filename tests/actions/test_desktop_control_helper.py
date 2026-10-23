"""Pointer motion may arrive after the RemoteDesktop portal call returns."""

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

from kyrin.actions.platforms import desktop_control
from kyrin.vision.capture_geometry import CaptureGeometry


@pytest.fixture
def helper(monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    gi = ModuleType("gi")
    repository = ModuleType("gi.repository")
    repository.Gio = ModuleType("Gio")
    repository.GLib = ModuleType("GLib")
    repository.Gio.DBusConnection = object
    monkeypatch.setitem(sys.modules, "gi", gi)
    monkeypatch.setitem(sys.modules, "gi.repository", repository)
    path = Path(desktop_control.__file__).with_name("desktop_control_helper.py")
    spec = importlib.util.spec_from_file_location("desktop_control_helper_test", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_waits_for_portal_pointer_motion(
    helper: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    frame = ("example.desktop", 42, 10, 20, 800, 600, 30, 40)
    observations = iter([frame, frame, (*frame[:6], 100, 120)])
    elapsed = 0.0

    def sleep(seconds: float) -> None:
        nonlocal elapsed
        elapsed += seconds

    monkeypatch.setattr(helper, "_window_and_pointer", lambda: next(observations))
    monkeypatch.setattr(helper, "_focused_identity", lambda: frame[:2])
    monkeypatch.setattr(helper, "monotonic", lambda: elapsed)
    monkeypatch.setattr(helper, "sleep", sleep)

    assert helper._wait_for_pointer(frame, 100, 120)
    assert elapsed == pytest.approx(0.1)


def test_wait_stops_if_window_moves(
    helper: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    frame = ("example.desktop", 42, 10, 20, 800, 600, 30, 40)
    monkeypatch.setattr(
        helper,
        "_window_and_pointer",
        lambda: ("example.desktop", 42, 11, 20, 800, 600, 100, 120),
    )
    monkeypatch.setattr(
        helper, "_focused_identity", lambda: pytest.fail("focus must not be read")
    )
    assert not helper._wait_for_pointer(frame, 100, 120)


def test_wait_times_out_when_pointer_does_not_arrive(
    helper: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    frame = ("example.desktop", 42, 10, 20, 800, 600, 30, 40)
    elapsed = 0.0

    def sleep(seconds: float) -> None:
        nonlocal elapsed
        elapsed += seconds

    monkeypatch.setattr(helper, "_window_and_pointer", lambda: frame)
    monkeypatch.setattr(helper, "monotonic", lambda: elapsed)
    monkeypatch.setattr(helper, "sleep", sleep)
    assert not helper._wait_for_pointer(frame, 100, 120)
    assert elapsed == pytest.approx(0.3)


def test_click_uses_actual_capture_origin_for_decorated_window(
    helper: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    frame = ("example.desktop", 42, 10, 20, 800, 600, 30, 40)
    calls: list[tuple[str, object]] = []

    class Bus:
        def call_sync(self, _bus, _object, _interface, method, arguments, *_rest):
            calls.append((method, arguments))

    helper.GLib.Variant = lambda _signature, value: value
    helper.Gio.DBusCallFlags = type("Flags", (), {"NONE": 0})
    observations = iter([frame, (*frame[:6], 132, 158)])
    monkeypatch.setattr(helper, "_window_and_pointer", lambda: next(observations))
    monkeypatch.setattr(helper, "_wait_for_pointer", lambda *_args: True)

    result = helper._click(
        Bus(), "/session", frame[:2], (100, 100, 40, 20, 796, 570),
        "Apply All Devices", None, False, None,
        (12, 48, 796, 570, 10, 20, 800, 600),
    )
    assert result == "CLICK_DISPATCHED"
    assert calls[0] == ("NotifyPointerMotion", ("/session", {}, 102.0, 118.0))
    assert [method for method, _args in calls[1:]] == [
        "NotifyPointerButton", "NotifyPointerButton"
    ]


def test_click_stops_if_capture_frame_moved(
    helper: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    frame = ("example.desktop", 42, 10, 20, 800, 600, 30, 40)
    monkeypatch.setattr(helper, "_window_and_pointer", lambda: frame)

    class Bus:
        def call_sync(self, *_args):
            pytest.fail("must not dispatch input after a frame change")

    assert helper._click(
        Bus(), "/session", frame[:2], (100, 100, 40, 20, 796, 570),
        "Apply All Devices", None, False, None,
        (12, 48, 796, 570, 11, 20, 800, 600),
    ) == "TARGET_CHANGED:frame_size"


def test_click_maps_small_png_area_size_difference(
    helper: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    frame = ("example.desktop", 42, 10, 20, 949, 656, 30, 40)
    motions: list[object] = []

    class Bus:
        def call_sync(self, _bus, _object, _interface, method, arguments, *_rest):
            if method == "NotifyPointerMotion":
                motions.append(arguments)

    helper.GLib.Variant = lambda _signature, value: value
    helper.Gio.DBusCallFlags = type("Flags", (), {"NONE": 0})
    observations = iter([frame, (*frame[:6], 591, 230)])
    monkeypatch.setattr(helper, "_window_and_pointer", lambda: next(observations))
    monkeypatch.setattr(helper, "_wait_for_pointer", lambda *_args: True)

    result = helper._click(
        Bus(), "/session", frame[:2], (541, 203, 94, 13, 960, 656),
        "Apply All Devices", None, False, None,
        (10, 20, 949, 656, 10, 20, 949, 656),
    )
    assert result == "CLICK_DISPATCHED"
    assert motions[0] == ("/session", {}, 561.0, 190.0)


@pytest.mark.parametrize(
    ("frame", "box", "capture", "expected_motion"),
    [
        (
            ("example.desktop", 42, 636, 253, 899, 606, 1200, 480),
            (566, 265, 94, 13, 949, 656),
            (636, 253, 899, 606, 636, 253, 899, 606),
            (24.0, 19.0),
        ),
        (
            ("example.desktop", 42, 10, 20, 800, 600, 100, 100),
            (190, 180, 100, 20, 820, 620),
            (10, 20, 800, 600, 10, 20, 800, 600),
            (140.0, 100.0),
        ),
    ],
)
def test_click_removes_symmetric_gnome_window_shadow(
    helper: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    frame: tuple[str, int, int, int, int, int, int, int],
    box: tuple[int, int, int, int, int, int],
    capture: tuple[int, int, int, int, int, int, int, int],
    expected_motion: tuple[float, float],
) -> None:
    motions: list[object] = []

    class Bus:
        def call_sync(self, _bus, _object, _interface, method, arguments, *_rest):
            if method == "NotifyPointerMotion":
                motions.append(arguments)

    helper.GLib.Variant = lambda _signature, value: value
    helper.Gio.DBusCallFlags = type("Flags", (), {"NONE": 0})
    observations = iter([
        frame,
        (*frame[:6], frame[6] + int(expected_motion[0]),
         frame[7] + int(expected_motion[1])),
    ])
    monkeypatch.setattr(helper, "_window_and_pointer", lambda: next(observations))
    monkeypatch.setattr(helper, "_wait_for_pointer", lambda *_args: True)

    result = helper._click(
        Bus(), "/session", frame[:2], box,
        "Example button", None, False, None, capture,
    )
    assert result == "CLICK_DISPATCHED"
    assert motions[0] == ("/session", {}, *expected_motion)


def test_click_rejects_large_png_area_size_difference(
    helper: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    frame = ("example.desktop", 42, 10, 20, 949, 656, 30, 40)
    monkeypatch.setattr(helper, "_window_and_pointer", lambda: frame)

    class Bus:
        def call_sync(self, *_args):
            pytest.fail("a large capture mismatch must not click")

    assert helper._click(
        Bus(), "/session", frame[:2], (541, 203, 94, 13, 1100, 656),
        "Apply All Devices", None, False, None,
        (10, 20, 949, 656, 10, 20, 949, 656),
    ) == "TARGET_CHANGED:image_scale_949x656_png_1100x656"


def test_click_uses_explicit_fractional_scale_instead_of_shadow_guess(
    helper: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    frame = ("example.desktop", 42, 10, 20, 400, 400, 0, 0)
    geometry = CaptureGeometry(
        "logical_desktop",
        0,
        (10, 20, 400, 400),
        (500, 500),
        1.25,
        1.25,
        (0, 0, 0, 0),
        (0, 0),
        (1, 1),
        "window-7",
        "capture-1",
        100.0,
        (10, 20, 400, 400),
    )
    motions: list[object] = []

    class Bus:
        def call_sync(self, _bus, _object, _interface, method, arguments, *_rest):
            if method == "NotifyPointerMotion":
                motions.append(arguments)

    helper.GLib.Variant = lambda _signature, value: value
    helper.Gio.DBusCallFlags = type("Flags", (), {"NONE": 0})
    observations = iter([frame, (*frame[:6], 110, 120)])
    monkeypatch.setattr(helper, "_window_and_pointer", lambda: next(observations))
    monkeypatch.setattr(helper, "_wait_for_pointer", lambda *_args: True)
    monkeypatch.setattr(
        helper, "_focused_window_token", lambda: "window-7", raising=False
    )
    monkeypatch.setattr(helper, "monotonic", lambda: 101.0)
    monkeypatch.setattr(helper, "_capture_still_current", lambda _id: True)
    assert (
        helper._click(
            Bus(),
            "/session",
            frame[:2],
            (120, 120, 10, 10, 500, 500),
            "Advanced",
            None,
            False,
            None,
            geometry,
        )
        == "CLICK_DISPATCHED"
    )
    assert motions == [("/session", {}, 110.0, 120.0)]


def test_click_rejects_stale_capture_before_pointer_motion(
    helper: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    frame = ("example.desktop", 42, 10, 20, 400, 400, 0, 0)
    geometry = CaptureGeometry(
        "logical_desktop",
        0,
        (10, 20, 400, 400),
        (400, 400),
        1,
        1,
        (0, 0, 0, 0),
        (0, 0),
        (1, 1),
        "window-7",
        "capture-1",
        100.0,
        (10, 20, 400, 400),
    )
    monkeypatch.setattr(helper, "_window_and_pointer", lambda: frame)
    monkeypatch.setattr(helper, "monotonic", lambda: 120.0)

    class Bus:
        def call_sync(self, *_args):
            pytest.fail("stale capture must not dispatch")

    assert (
        helper._click(
            Bus(),
            "/session",
            frame[:2],
            (100, 100, 20, 20, 400, 400),
            "Advanced",
            None,
            False,
            None,
            geometry,
        )
        == "TARGET_CHANGED:stale_capture"
    )


def test_click_rejects_same_app_and_pid_with_different_window_token(
    helper: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    frame = ("example.desktop", 42, 10, 20, 400, 400, 0, 0)
    geometry = CaptureGeometry(
        "logical_desktop",
        0,
        (10, 20, 400, 400),
        (400, 400),
        1,
        1,
        (0, 0, 0, 0),
        (0, 0),
        (1, 1),
        "window-7",
        "capture-1",
        100.0,
        (10, 20, 400, 400),
    )
    monkeypatch.setattr(helper, "_window_and_pointer", lambda: frame)
    monkeypatch.setattr(
        helper, "_focused_window_token", lambda: "window-8", raising=False
    )
    monkeypatch.setattr(helper, "monotonic", lambda: 101.0)

    class Bus:
        def call_sync(self, *_args):
            pytest.fail("changed window must not dispatch")

    assert (
        helper._click(
            Bus(),
            "/session",
            frame[:2],
            (100, 100, 20, 20, 400, 400),
            "Advanced",
            None,
            False,
            None,
            geometry,
        )
        == "TARGET_CHANGED:window_token"
    )


def test_changed_content_after_input_grant_blocks_click(
    helper: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    frame = ("example.desktop", 42, 10, 20, 400, 400, 0, 0)
    geometry = CaptureGeometry(
        "logical_desktop", 0, (10, 20, 400, 400), (400, 400),
        1, 1, (0, 0, 0, 0), (0, 0), (1, 1),
        "window-7", "capture-1", 100.0, (10, 20, 400, 400),
    )
    monkeypatch.setattr(helper, "_window_and_pointer", lambda: frame)
    monkeypatch.setattr(helper, "_focused_window_token", lambda: "window-7")
    monkeypatch.setattr(
        helper, "_capture_still_current", lambda _id: False, raising=False
    )
    monkeypatch.setattr(helper, "monotonic", lambda: 101.0)

    class Bus:
        def call_sync(self, *_args):
            pytest.fail("changed content must not dispatch")

    assert helper._click(
        Bus(), "/session", frame[:2], (100, 100, 20, 20, 400, 400),
        "Advanced", None, False, None, geometry,
    ) == "TARGET_CHANGED:content"


def test_final_pointer_must_reach_target_before_button(
    helper: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    frame = ("example.desktop", 42, 10, 20, 800, 600, 0, 0)
    observations = iter([frame, (*frame[:6], 125, 135)])
    monkeypatch.setattr(helper, "_window_and_pointer", lambda: next(observations))
    monkeypatch.setattr(helper, "_wait_for_pointer", lambda *_args: True)
    helper.GLib.Variant = lambda _signature, value: value
    helper.Gio.DBusCallFlags = type("Flags", (), {"NONE": 0})
    calls: list[str] = []

    class Bus:
        def call_sync(self, _bus, _object, _interface, method, *_rest):
            calls.append(method)

    assert helper._click(
        Bus(), "/session", frame[:2], (100, 100, 20, 20, 800, 600),
        "Advanced", None, False, None,
    ) == "TARGET_CHANGED:pointer_or_window"
    assert calls == ["NotifyPointerMotion"]


def test_legacy_capture_reports_missing_geometry_instead_of_window_movement(
    helper: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    frame = ("example.desktop", 42, 10, 20, 800, 600, 30, 40)
    monkeypatch.setattr(helper, "_window_and_pointer", lambda: frame)

    class Bus:
        def call_sync(self, *_args):
            pytest.fail("legacy capture with unmatched dimensions must not click")

    assert helper._click(
        Bus(), "/session", frame[:2], (100, 100, 40, 20, 796, 570),
        "Apply All Devices", None, False, None,
    ) == "CAPTURE_GEOMETRY_REQUIRED"
