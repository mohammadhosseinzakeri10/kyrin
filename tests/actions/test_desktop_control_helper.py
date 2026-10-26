"""Pointer motion may arrive after the RemoteDesktop portal call returns."""

import importlib.util
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

from kyrin.actions.platforms import desktop_control
from kyrin.vision.capture_geometry import CaptureGeometry
from tests.desktop.test_backend_protocol import bus_reply


@pytest.fixture
def helper(monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    gi = ModuleType("gi")
    repository = ModuleType("gi.repository")
    monkeypatch.setattr(repository, "Gio", ModuleType("Gio"), raising=False)
    monkeypatch.setattr(repository, "GLib", ModuleType("GLib"), raising=False)
    monkeypatch.setattr(repository.Gio, "DBusConnection", object, raising=False)
    monkeypatch.setitem(sys.modules, "gi", gi)
    monkeypatch.setitem(sys.modules, "gi.repository", repository)
    path = Path(desktop_control.__file__).with_name("desktop_control_helper.py")
    spec = importlib.util.spec_from_file_location("desktop_control_helper_test", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    def handshake_transport(
        args: list[str], **kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        assert args[-1] == "GetCapabilities", "unexpected unmocked desktop call"
        return bus_reply(
            "GetActiveWindow", "GetActiveWindowToken", "GetActiveWindowAndPointer",
            "ValidateCapture", "ValidateCaptureRegions", "capture-geometry-v1",
        )

    monkeypatch.setattr(module, "run_process", handshake_transport)

    # Geometry tests model a widget without an accessibility action.
    monkeypatch.setattr(module, "_accessible_control", lambda *_a, **_k: None)
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
        def call_sync(
            self,
            _bus: str,
            _object: str,
            _interface: str,
            method: str,
            arguments: object,
            *_rest: object,
        ) -> None:
            calls.append((method, arguments))

    helper.GLib.Variant = lambda _signature, value: value
    helper.Gio.DBusCallFlags = type("Flags", (), {"NONE": 0})
    observations = iter([frame, (*frame[:6], 132, 158)])
    monkeypatch.setattr(helper, "_window_and_pointer", lambda: next(observations))
    monkeypatch.setattr(helper, "_wait_for_pointer", lambda *_args: True)

    result = helper._click(
        Bus(),
        "/session",
        frame[:2],
        (100, 100, 40, 20, 796, 570),
        "Apply All Devices",
        None,
        False,
        None,
        (12, 48, 796, 570, 10, 20, 800, 600),
    )
    assert result == "CLICK_DISPATCHED"
    assert calls[0] == ("NotifyPointerMotion", ("/session", {}, 102.0, 118.0))
    assert [method for method, _args in calls[1:]] == [
        "NotifyPointerButton",
        "NotifyPointerButton",
    ]


def test_click_stops_if_capture_frame_moved(
    helper: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    frame = ("example.desktop", 42, 10, 20, 800, 600, 30, 40)
    monkeypatch.setattr(helper, "_window_and_pointer", lambda: frame)

    class Bus:
        def call_sync(self, *_args: object) -> None:
            pytest.fail("must not dispatch input after a frame change")

    assert (
        helper._click(
            Bus(),
            "/session",
            frame[:2],
            (100, 100, 40, 20, 796, 570),
            "Apply All Devices",
            None,
            False,
            None,
            (12, 48, 796, 570, 11, 20, 800, 600),
        )
        == "TARGET_CHANGED:frame_size"
    )


@pytest.mark.parametrize(
    ("capture_size", "image_size"),
    [((949, 656), (960, 656)), ((899, 606), (949, 656)),
     ((800, 600), (820, 620)), ((949, 656), (1100, 656)),
     ((800, 600), (801, 600))],
)
def test_legacy_click_rejects_unproven_scale_or_shadow(
    helper: ModuleType, monkeypatch: pytest.MonkeyPatch,
    capture_size: tuple[int, int], image_size: tuple[int, int],
) -> None:
    frame = ("example.desktop", 42, 10, 20, *capture_size, 30, 40)
    monkeypatch.setattr(helper, "_window_and_pointer", lambda: frame)

    class Bus:
        def call_sync(self, *_args: object) -> None:
            pytest.fail("legacy dimensions cannot establish scale or shadow origin")

    assert helper._click(
        Bus(), "/session", frame[:2], (100, 100, 40, 20, *image_size),
        "Example button", None, False, None,
        (*frame[2:6], *frame[2:6]),
    ) == "CAPTURE_GEOMETRY_REQUIRED"


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
        (20, 30),
        (2, 2),
        "window-7",
        "capture-1",
        100.0,
        (10, 20, 400, 400),
    )
    motions: list[object] = []

    class Bus:
        def call_sync(
            self,
            _bus: str,
            _object: str,
            _interface: str,
            method: str,
            arguments: object,
            *_rest: object,
        ) -> None:
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
    validated: list[tuple[str, tuple[tuple[int, int, int, int], ...]]] = []

    def validate(
        capture_id: str, regions: tuple[tuple[int, int, int, int], ...]
    ) -> bool:
        validated.append((capture_id, regions))
        return True
    monkeypatch.setattr(
        helper,
        "_capture_still_current",
        validate,
    )
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
    assert validated == [("capture-1", ((120, 120, 10, 10),))]


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
        def call_sync(self, *_args: object) -> None:
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
        def call_sync(self, *_args: object) -> None:
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
    monkeypatch.setattr(helper, "_focused_window_token", lambda: "window-7")
    monkeypatch.setattr(
        helper, "_capture_still_current", lambda _id, _regions: False, raising=False
    )
    monkeypatch.setattr(helper, "monotonic", lambda: 101.0)

    class Bus:
        def call_sync(self, *_args: object) -> None:
            pytest.fail("changed content must not dispatch")

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
        == "TARGET_CHANGED:content"
    )


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
        def call_sync(
            self, _bus: str, _object: str, _interface: str, method: str, *_rest: object
        ) -> None:
            calls.append(method)

    assert (
        helper._click(
            Bus(),
            "/session",
            frame[:2],
            (100, 100, 20, 20, 800, 600),
            "Advanced",
            None,
            False,
            None,
        )
        == "TARGET_CHANGED:pointer_or_window"
    )
    assert calls == ["NotifyPointerMotion"]


def test_legacy_capture_reports_missing_geometry_instead_of_window_movement(
    helper: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    frame = ("example.desktop", 42, 10, 20, 800, 600, 30, 40)
    monkeypatch.setattr(helper, "_window_and_pointer", lambda: frame)

    class Bus:
        def call_sync(self, *_args: object) -> None:
            pytest.fail("legacy capture with unmatched dimensions must not click")

    assert (
        helper._click(
            Bus(),
            "/session",
            frame[:2],
            (100, 100, 40, 20, 796, 570),
            "Apply All Devices",
            None,
            False,
            None,
        )
        == "CAPTURE_GEOMETRY_REQUIRED"
    )


def test_accessibility_also_rejects_replaced_same_app_window(
    helper: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
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
    monkeypatch.setattr(helper, "_focused_window_token", lambda: "window-8")
    monkeypatch.setattr(helper, "monotonic", lambda: 101.0)
    monkeypatch.setattr(
        helper,
        "_accessible_control",
        lambda *_a, **_k: (None, None, True, True, (110, 130)),
    )

    class Bus:
        def call_sync(self, *_args: object) -> None:
            pytest.fail("replaced window must not receive input")

    assert (
        helper._click(
            Bus(),
            "/session",
            frame[:2],
            (0, 0, 0, 0, 0, 0),
            "Advanced",
            True,
            True,
            (100, 110),
            geometry,
        )
        == "TARGET_CHANGED:window_token"
    )


@pytest.mark.parametrize("accessible", [True, False])
def test_window_switch_after_shared_session_acquire_rejects_original_request(
    helper: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    accessible: bool,
) -> None:
    from kyrin.desktop.window_observation import WindowObservation

    observation = WindowObservation(
        "example.desktop", 42, "window-7", "initial", 100, 110
    )
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
        100,
        (10, 20, 400, 400),
    )
    token = ["window-7"]
    calls: list[str] = []

    class Bus:
        def rotate(self, value: str) -> None:
            assert value == "replacement"

        def close(self) -> None:
            pass

        def call_sync(
            self, _bus: str, _object: str, _interface: str, method: str, *_rest: object
        ) -> None:
            calls.append(method)
            assert method == "Close", "must not send any Notify after switching windows"

    def acquire(_devices: int) -> tuple[Bus, str]:
        token[0] = "window-8"
        return Bus(), "/session"

    monkeypatch.setattr(helper, "shared_session", acquire)
    monkeypatch.setattr(helper, "_wait_for_expected_focus", lambda *_a: True)
    monkeypatch.setattr(helper, "_focused_identity", lambda: observation.identity)
    monkeypatch.setattr(helper, "_focused_window_token", lambda: token[0])
    monkeypatch.setattr(
        helper,
        "_window_and_pointer",
        lambda: (*observation.identity, 10, 20, 400, 400, 0, 0),
    )
    monkeypatch.setattr(helper, "monotonic", lambda: 101)
    box = (0, 0, 0, 0, 0, 0) if accessible else (100, 100, 20, 20, 400, 400)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "helper",
            *map(str, observation.identity),
            *map(str, box),
            "click",
            "Settings",
            "accessible" if accessible else "visible",
            "observation=" + observation.to_json(),
            *([] if accessible else ["geometry=" + geometry.to_json()]),
        ],
    )
    assert helper.main() == 2
    assert calls == []


@pytest.mark.parametrize("change", ["window", "deadline", "missing"])
def test_accessibility_checks_original_evidence_again_before_pressing(
    helper: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    change: str,
) -> None:
    from kyrin.desktop.window_observation import WindowObservation

    observation = WindowObservation(
        "example.desktop", 42, "window-7", "initial", 100, 110
    )
    frame = (*observation.identity, 10, 20, 400, 400, 0, 0)
    frames = iter([frame, (*frame[:6], 110, 130)])
    token: list[str | None] = [observation.window_token]
    now = [101.0]
    calls: list[str] = []

    class Bus:
        def call_sync(
            self, _bus: str, _object: str, _interface: str, method: str, *_rest: object
        ) -> None:
            calls.append(method)

    def wait(*_args: object) -> bool:
        if change == "deadline":
            now[0] = observation.deadline
        else:
            token[0] = "window-8" if change == "window" else None
        return True

    helper.GLib.Variant = lambda _signature, value: value
    helper.Gio.DBusCallFlags = type("Flags", (), {"NONE": 0})
    monkeypatch.setattr(helper, "_window_and_pointer", lambda: next(frames))
    monkeypatch.setattr(helper, "_focused_window_token", lambda: token[0])
    monkeypatch.setattr(helper, "_wait_for_pointer", wait)
    monkeypatch.setattr(
        helper,
        "_accessible_control",
        lambda *_a, **_k: (None, None, True, None, (110, 130)),
    )
    monkeypatch.setattr(helper, "monotonic", lambda: now[0])
    result = helper._click(
        Bus(),
        "/session",
        observation.identity,
        (0, 0, 0, 0, 0, 0),
        "Settings",
        None,
        True,
        None,
        observation=observation,
    )
    assert result == (
        "TARGET_CHANGED:stale_capture"
        if change == "deadline"
        else "TARGET_CHANGED:window_token"
    )
    assert calls == ["NotifyPointerMotion"]
