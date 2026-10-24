"""The keyboard portal waits for Telegram focus without a fixed ten-second delay."""

import importlib.util
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

from kyrin.actions.platforms import telegram
from kyrin.app.permission_token import read_opaque_token, save_opaque_token
from kyrin.vision.capture_geometry import CaptureGeometry
from tests.desktop.test_backend_protocol import bus_reply


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
    def handshake_transport(args, **kwargs):
        assert args[-1] == "GetCapabilities", "unexpected unmocked desktop call"
        return bus_reply(
            "GetActiveWindow", "GetActiveWindowToken", "GetActiveWindowAndPointer",
            "ValidateCapture", "ValidateCaptureRegions", "capture-geometry-v1",
        )

    monkeypatch.setattr(module, "run_process", handshake_transport)

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


def test_portal_restores_and_rotates_control_token_for_keyboard_action(
    helper: ModuleType, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    token_path = tmp_path / "telegram-control.token"
    save_opaque_token(token_path, "old-opaque-token")
    monkeypatch.setattr(helper, "CONTROL_TOKEN_PATH", token_path)
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
        return {"devices": 3, "restore_token": "next-opaque-token"}

    monkeypatch.setattr(helper, "_request", request)
    assert helper.main() == 0
    assert calls[1][0] == "SelectDevices"
    options = calls[1][1][1]
    assert options["types"] == ("u", 3)
    assert options["persist_mode"] == ("u", 2)
    assert options["restore_token"] == ("s", "old-opaque-token")
    assert read_opaque_token(token_path) == "next-opaque-token"


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


def test_settings_click_keeps_stricter_region_than_chat_click(
    helper: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    expected = ("org.telegram.desktop", 42)
    observations = iter(
        [
            (*expected, 100, 50, 1600, 900, 500, 300),
            (*expected, 100, 50, 1600, 900, 742, 267),
        ]
    )
    monkeypatch.setattr(helper, "_window_and_pointer", lambda: next(observations))
    monkeypatch.setattr(helper, "sleep", lambda _seconds: None)
    helper.GLib.Variant = lambda signature, value: (signature, value)

    class Bus:
        def call_sync(self, *_args: object) -> None:
            return None

    helper.Gio.DBusCallFlags = type("Flags", (), {"NONE": 0})
    box = (540, 205, 205, 24, 1600, 900)
    assert not helper._click_verified_box(Bus(), "/session", expected, box)
    assert helper._click_verified_box(
        Bus(), "/session", expected, box, settings_item=True
    )


def test_pointer_accepts_first_chat_row_but_rejects_search_field(
    helper: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    expected = ("org.telegram.desktop", 42)
    observations = iter(
        [
            (*expected, 100, 50, 1920, 1080, 500, 300),
            (*expected, 100, 50, 1920, 1080, 199, 148),
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
    assert not helper._click_verified_box(
        Bus(), "/session", expected, (67, 45, 65, 13, 1920, 1080)
    )
    assert helper._click_verified_box(
        Bus(), "/session", expected, (67, 92, 65, 13, 1920, 1080)
    )
    assert calls == [
        "NotifyPointerMotion",
        "NotifyPointerButton",
        "NotifyPointerButton",
    ]


def test_visible_row_can_be_clicked_near_bottom_but_search_result_cannot(
    helper: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    expected = ("org.telegram.desktop", 42)
    observations = iter([
        (*expected, 100, 50, 1600, 900, 500, 300),
        (*expected, 100, 50, 1600, 900, 215, 812),
    ])
    monkeypatch.setattr(helper, "_window_and_pointer", lambda: next(observations))
    monkeypatch.setattr(helper, "sleep", lambda _seconds: None)
    helper.GLib.Variant = lambda signature, value: (signature, value)
    helper.Gio.DBusCallFlags = type("Flags", (), {"NONE": 0})

    class Bus:
        def call_sync(self, *_args: object) -> None:
            return None

    box = (70, 750, 90, 24, 1600, 900)
    assert not helper._click_verified_box(Bus(), "/session", expected, box)
    assert helper._click_verified_box(
        Bus(), "/session", expected, box, visible_row=True
    )


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


def test_telegram_click_uses_shared_capture_geometry(
    helper: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    expected = ("org.telegram.desktop", 42)
    frame = (*expected, -1200, 20, 800, 600, -900, 300)
    geometry = CaptureGeometry(
        "logical_desktop",
        1,
        (-1200, 20, 800, 600),
        (1020, 770),
        1.25,
        1.25,
        (10, 10, 10, 10),
        (0, 0),
        (1, 1),
        "window-7",
        "capture-1",
        100.0,
        (-1200, 20, 800, 600),
    )
    observations = iter([frame, (*frame[:6], -1100, 120)])
    monkeypatch.setattr(helper, "_window_and_pointer", lambda: next(observations))
    monkeypatch.setattr(helper, "_focused_window_token", lambda: "window-7")
    monkeypatch.setattr(helper, "monotonic", lambda: 101.0)
    validations = []
    monkeypatch.setattr(
        helper, "_capture_still_current",
        lambda capture_id, regions: validations.append((capture_id, regions)) or True,
    )
    monkeypatch.setattr(helper, "sleep", lambda _seconds: None)
    helper.GLib.Variant = lambda _signature, value: value
    helper.Gio.DBusCallFlags = type("Flags", (), {"NONE": 0})
    calls: list[object] = []

    class Bus:
        def call_sync(self, _bus, _object, _interface, method, arguments, *_rest):
            calls.append((method, arguments))

    assert helper._click_verified_box(
        Bus(),
        "/session",
        expected,
        (120, 120, 30, 30, 1020, 770),
        geometry=geometry,
        evidence_regions=((120, 120, 30, 30), (500, 400, 20, 20)),
    )
    assert validations == [
        ("capture-1", ((120, 120, 30, 30), (500, 400, 20, 20))),
    ]
    assert calls[0] == ("NotifyPointerMotion", ("/session", {}, -200.0, -180.0))


def test_window_token_is_read_from_user_bus(
    helper: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    commands: list[list[str]] = []

    def run(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        if args[-1] == "GetCapabilities":
            return bus_reply(
                "GetActiveWindowToken", "ValidateCapture", "ValidateCaptureRegions",
                "capture-geometry-v1",
            )
        commands.append(args)
        return subprocess.CompletedProcess(args, 0, '{"type":"s","data":["17"]}', "")

    monkeypatch.setattr(helper, "run_process", run)
    assert helper._focused_window_token() == "17"
    assert commands[0][:4] == ["busctl", "--user", "--json=short", "call"]


def test_capture_validation_uses_capture_id_on_user_bus(
    helper: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    commands: list[list[str]] = []

    def run(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        if args[-1] == "GetCapabilities":
            return bus_reply(
                "GetActiveWindowToken", "ValidateCapture", "ValidateCaptureRegions",
                "capture-geometry-v1",
            )
        commands.append(args)
        return subprocess.CompletedProcess(args, 0, '{"type":"b","data":[true]}', "")

    monkeypatch.setattr(helper, "run_process", run)
    assert helper._capture_still_current("capture-1")
    assert commands[0][-3:] == ["ValidateCapture", "s", "capture-1"]


def test_telegram_rejects_same_pid_new_window_before_button(
    helper: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    expected = ("org.telegram.desktop", 42)
    frame = (*expected, 10, 20, 800, 600, 0, 0)
    geometry = CaptureGeometry(
        "logical_desktop",
        0,
        (10, 20, 800, 600),
        (800, 600),
        1,
        1,
        (0, 0, 0, 0),
        (0, 0),
        (1, 1),
        "window-7",
        "capture-1",
        100.0,
        (10, 20, 800, 600),
    )
    observations = iter([frame, (*frame[:6], 100, 120)])
    tokens = iter(["window-7", "window-8"])
    monkeypatch.setattr(helper, "_window_and_pointer", lambda: next(observations))
    monkeypatch.setattr(helper, "_focused_window_token", lambda: next(tokens))
    monkeypatch.setattr(helper, "monotonic", lambda: 101.0)
    monkeypatch.setattr(helper, "_capture_still_current", lambda _id, _regions: True)
    monkeypatch.setattr(helper, "sleep", lambda _seconds: None)
    helper.GLib.Variant = lambda _signature, value: value
    helper.Gio.DBusCallFlags = type("Flags", (), {"NONE": 0})
    calls: list[str] = []

    class Bus:
        def call_sync(self, _bus, _object, _interface, method, *_rest):
            calls.append(method)

    assert not helper._click_verified_box(
        Bus(),
        "/session",
        expected,
        (70, 90, 40, 20, 800, 600),
        geometry=geometry,
    )
    assert calls == ["NotifyPointerMotion"]


def test_pointer_grant_restores_and_rotates_token_when_enabled(
    helper: ModuleType, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    expected = ("org.telegram.desktop", 42)
    token_path = tmp_path / "telegram-control.token"
    save_opaque_token(token_path, "old-pointer-token")
    monkeypatch.setattr(helper, "CONTROL_TOKEN_PATH", token_path)
    monkeypatch.setattr(
        helper.sys,
        "argv",
        [
            "helper", expected[0], "42", "click", "70", "220", "90", "24",
            "1600", "900",
        ],
    )
    monkeypatch.setattr(helper, "_focused_identity", lambda: expected)
    monkeypatch.setattr(helper, "_wait_for_expected_focus", lambda _identity: True)
    from json import dumps

    geometry = CaptureGeometry(
        "logical_desktop", 0, (0, 0, 1600, 900), (1600, 900), 1, 1,
        (0, 0, 0, 0), (0, 0), (1, 1), "window-7", "capture-1", 100.0,
    )
    monkeypatch.setattr(helper.sys, "argv", [
        *helper.sys.argv,
        "evidence=" + dumps(((70, 220, 90, 24), (300, 220, 20, 20))),
        "geometry=" + geometry.to_json(),
    ])
    validated = []
    monkeypatch.setattr(
        helper, "_click_verified_box",
        lambda *_args, **kwargs: validated.append(kwargs) or True,
    )
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
        return {"devices": 3, "restore_token": "next-pointer-token"}

    monkeypatch.setattr(helper, "_request", request)
    assert helper.main() == 0
    options = calls[1][1][1]
    assert options["types"] == ("u", 3)
    assert options["persist_mode"] == ("u", 2)
    assert options["restore_token"] == ("s", "old-pointer-token")
    assert read_opaque_token(token_path) == "next-pointer-token"
    assert validated[0]["geometry"] == geometry
    assert validated[0]["evidence_regions"] == (
        (70, 220, 90, 24), (300, 220, 20, 20),
    )


def test_setup_grants_control_without_focusing_or_clicking_telegram(
    helper: ModuleType, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    token_path = tmp_path / "telegram-control.token"
    monkeypatch.setattr(helper, "CONTROL_TOKEN_PATH", token_path)
    monkeypatch.setattr(helper.sys, "argv", ["helper", "grant-control"])
    monkeypatch.setattr(
        helper, "_focused_identity", lambda: pytest.fail("no chat focus is needed")
    )
    monkeypatch.setattr(
        helper, "_click_verified_box",
        lambda *_args: pytest.fail("setup must not click"),
    )
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
        return {"devices": 3, "restore_token": "saved-control-token"}

    monkeypatch.setattr(helper, "_request", request)
    assert helper.main() == 0
    assert calls[1][1][1]["types"] == ("u", 3)
    assert calls[1][1][1]["persist_mode"] == ("u", 2)
    assert read_opaque_token(token_path) == "saved-control-token"


@pytest.mark.parametrize(
    "arguments",
    [
        [],
        ["search", "My Mother"],
        ["click", "70", "220", "90", "24", "1600", "900"],
    ],
)
def test_actions_without_setup_do_not_request_control_portal(
    helper: ModuleType, monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
    arguments: list[str],
) -> None:
    expected = ("org.telegram.desktop", 42)
    monkeypatch.setattr(helper, "CONTROL_TOKEN_PATH", tmp_path / "missing.token")
    monkeypatch.setattr(helper.sys, "argv", ["helper", expected[0], "42", *arguments])
    monkeypatch.setattr(helper, "_focused_identity", lambda: expected)
    helper.Gio.bus_get_sync = lambda *_args: type(
        "Bus", (), {"call_sync": lambda *_args: None}
    )()
    helper.Gio.BusType = type("BusType", (), {"SESSION": 0})
    helper.Gio.DBusCallFlags = type("Flags", (), {"NONE": 0})
    helper.GLib.Variant = lambda signature, value: (signature, value)
    calls: list[str] = []

    def request(_connection, method, _arguments, _timeout):
        calls.append(method)
        return {"session_handle": "/test/session"}

    monkeypatch.setattr(helper, "_request", request)
    assert helper.main() == 3
    assert calls == []


def test_capture_validation_sends_disjoint_source_pixel_evidence(
    helper: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    commands: list[list[str]] = []

    def run(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        if args[-1] == "GetCapabilities":
            return bus_reply(
                "GetActiveWindowToken", "ValidateCapture", "ValidateCaptureRegions",
                "capture-geometry-v1",
            )
        commands.append(args)
        return subprocess.CompletedProcess(args, 0, '{"type":"b","data":[true]}', "")

    monkeypatch.setattr(helper, "run_process", run)
    assert helper._capture_still_current(
        "capture-1", ((120, 80, 30, 10), (40, 20, 8, 8))
    )
    assert commands[0][-12:] == [
        "ValidateCaptureRegions", "sa(iiii)", "capture-1", "2",
        "120", "80", "30", "10", "40", "20", "8", "8",
    ]


@pytest.mark.parametrize(
    "regions",
    [(), ((100, 100, 20, 20),), ((70, 220, 90, 24), (1590, 0, 20, 10)),
     ((70, 220, 90, 24), (-1, 0, 10, 10))],
)
def test_telegram_rejects_missing_target_or_outside_evidence_before_input(
    helper: ModuleType, regions: tuple[tuple[int, int, int, int], ...]
) -> None:
    geometry = CaptureGeometry(
        "logical_desktop", 0, (0, 0, 1600, 900), (1600, 900), 1, 1,
        (0, 0, 0, 0), (0, 0), (1, 1), "window-7", "capture-1", 100.0,
    )
    class Bus:
        def call_sync(self, *_args):
            pytest.fail("invalid evidence must not dispatch input")

    assert not helper._click_verified_box(
        Bus(),
        "/session",
        ("telegram.desktop", 42),
        (70, 220, 90, 24, 1600, 900),
        geometry=geometry,
        evidence_regions=regions,
    )


def test_revocation_after_portal_start_closes_session_without_input_or_token_restore(
    helper: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from kyrin.operations import OperationStopped

    path = tmp_path / "telegram-control.token"
    save_opaque_token(path, "old")
    monkeypatch.setattr(helper, "CONTROL_TOKEN_PATH", path)
    monkeypatch.setattr(helper.sys, "argv", ["helper", "org.telegram.desktop", "42"])
    monkeypatch.setattr(
        helper, "_focused_identity", lambda: ("org.telegram.desktop", 42)
    )
    sent = []

    class Bus:
        def call_sync(self, *args):
            sent.append(args[3])

    helper.Gio.bus_get_sync = lambda *args: Bus()
    helper.Gio.BusType = type("BusType", (), {"SESSION": 0})
    helper.Gio.DBusCallFlags = type("Flags", (), {"NONE": 0})
    helper.GLib.Variant = lambda signature, value: value
    helper.GLib.Error = RuntimeError

    def request(connection, method, arguments, timeout):
        if method == "CreateSession":
            return {"session_handle": "/session"}
        if method == "SelectDevices":
            return {}
        path.unlink()
        return {"devices": 3, "restore_token": "late"}

    monkeypatch.setattr(helper, "_request", request)
    with pytest.raises(OperationStopped):
        helper.main()
    assert sent == ["Close"]
    assert not path.exists()


def test_portal_request_timeout_closes_request_and_ignores_late_response(
    helper: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from kyrin.actions.platforms.helper_lifecycle import HelperLifetime

    timers = []
    replies = []
    unsubscribed = []
    calls = []
    path = []

    class Loop:
        def run(self):
            timers[0][1]()

        def quit(self):
            replies.append("quit")

    class Reply:
        def unpack(self):
            return (path[0],)

    class Bus:
        def get_unique_name(self):
            return ":1.123"

        def signal_subscribe(self, *args):
            path.append(args[3])
            self.late_response = args[-1]
            return 123

        def signal_unsubscribe(self, identifier):
            unsubscribed.append(identifier)

        def call_sync(self, *args):
            calls.append(args)
            return Reply()

    bus = Bus()
    helper.GLib.MainLoop = Loop
    helper.GLib.timeout_add = lambda duration, callback: (
        timers.append((duration, callback)) or 1
    )
    helper.GLib.source_remove = lambda identifier: None
    helper.GLib.Variant = lambda signature, value: value
    helper.GLib.VariantType = type(
        "VariantType", (), {"new": staticmethod(lambda s: s)}
    )
    helper.GLib.Error = RuntimeError
    helper.Gio.DBusSignalFlags = type("Flags", (), {"NONE": 0})
    helper.Gio.DBusCallFlags = type("Flags", (), {"NONE": 0})
    lifetime = HelperLifetime(bus, tmp_path / "token", None)
    try:
        now = [0.0]
        lifetime.operation.clock = lambda: now[0]
        lifetime.operation.deadline = 1.0
        assert helper._request(lifetime, "Start", ("/session", "", {}), 30000) is None
        assert timers[0][0] == 1000
        assert [call[3] for call in calls] == ["Start", "Close"]
        assert calls[-1][1] == path[0]
        assert unsubscribed == [123]

        class Late:
            def unpack(self):
                pytest.fail("a completed request must ignore late response data")

        bus.late_response(None, None, None, None, None, Late())
        assert replies == ["quit"]
    finally:
        lifetime.close()


def test_unbound_search_never_sends_text(
    helper: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    keys: list[int] = []
    monkeypatch.setattr(helper, "_key", lambda _c, _s, key, down: keys.append(key))
    monkeypatch.setattr(helper, "sleep", lambda _s: None)
    with pytest.raises(ValueError, match="identity"):
        helper._type_search_target(object(), "/session", "Ali")
    assert keys == []


def test_focus_change_during_search_never_sends_remaining_characters(
    helper: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    expected = ("org.telegram.desktop", 42)
    sent: list[int] = []
    monkeypatch.setattr(helper, "sleep", lambda _s: None)
    monkeypatch.setattr(helper, "_focus_search", lambda *_a: None)
    monkeypatch.setattr(helper, "_focused_identity", lambda: ("other.desktop", 10))
    monkeypatch.setattr(helper, "_key", lambda _c, _s, key, down: sent.append(key))
    with pytest.raises(ValueError):
        helper._type_search_target(object(), "/session", "Ali", expected)
    assert sent == []
