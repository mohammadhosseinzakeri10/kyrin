"""One-shot Telegram chat input with remembered portal consent.

Only search mode edits a bound accessible field in cancellable batches; it
never presses Enter or sends a message. Menu activation uses a live semantic
control. Pointer mode clicks one OCR-approved search result after
fresh focus, geometry, and pointer-position checks. Run with system Python
for Ubuntu's Gio bindings. The application owner retains the live session.
"""

import json
import subprocess
import sys
from pathlib import Path
from time import monotonic, sleep
from typing import Any
from uuid import uuid4

# A read-only handshake must not import GI or open a desktop connection.
if __name__ == "__main__" and sys.argv[1:] == ["--capabilities"]:
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
    from kyrin.backend_protocol import helper_manifest

    print(helper_manifest("telegram_portal-v1"))
    raise SystemExit(0)

from gi.repository import Gio, GLib  # type: ignore[import-not-found]

# This helper uses Ubuntu's system Python for GI even when KYRIN runs in a venv.
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from kyrin.actions.platforms.desktop_accessibility import (  # noqa: E402
    ControlUnavailable,
    action_index,
)
from kyrin.actions.platforms.helper_lifecycle import (  # noqa: E402
    HelperLifetime,
    shared_session,
)
from kyrin.actions.platforms.telegram_accessibility import (  # noqa: E402
    TelegramControl,
    locate_control,
)
from kyrin.app.permission_token import (  # noqa: E402
    permission_token_path,
)
from kyrin.backend_protocol import BackendUnavailable, probe_gnome  # noqa: E402
from kyrin.desktop.platforms.gnome import read_active_window_token  # noqa: E402
from kyrin.operations import remaining, run_process  # noqa: E402
from kyrin.vision.capture_geometry import (  # noqa: E402
    CaptureGeometry,
    Rect,
    capture_is_current,
    capture_regions_valid,
    coordinate_to_desktop,
)

BUS = "org.freedesktop.portal.Desktop"
OBJECT = "/org/freedesktop/portal/desktop"
REMOTE = "org.freedesktop.portal.RemoteDesktop"
REQUEST = "org.freedesktop.portal.Request"
SESSION = "org.freedesktop.portal.Session"
SHELL = "org.gnome.Shell"
SHELL_OBJECT = "/org/kyrin/ActiveApp"
SHELL_INTERFACE = "org.kyrin.ActiveApp"
SCREEN_OBJECT = "/org/kyrin/WindowCapturePrototype"
SCREEN_INTERFACE = "org.kyrin.WindowCapturePrototype"
CONTROL = 0xFFE3
ESCAPE = 0xFF1B
ZERO = ord("0")
NINE = ord("9")
J_KEY = ord("j")
LEFT_BUTTON = 0x110
CONTROL_TOKEN_PATH = permission_token_path("telegram-control")


def _request(
    connection: Gio.DBusConnection,
    method: str,
    arguments: tuple[Any, ...],
    timeout_ms: int,
) -> dict[str, Any] | None:
    timeout_ms = max(1, int(remaining(timeout_ms / 1000) * 1000))
    token = "kyrin_" + uuid4().hex
    sender = connection.get_unique_name().replace(":", "").replace(".", "_")
    path = f"/org/freedesktop/portal/desktop/request/{sender}/{token}"
    loop = GLib.MainLoop()
    response: list[tuple[int, dict[str, Any]]] = []
    accepting = True
    timed_out = False

    def on_response(_connection, _sender, _path, _interface, _signal, parameters):  # type: ignore[no-untyped-def]
        if accepting and not timed_out and not response:
            response.append(parameters.unpack())
            loop.quit()

    subscription = connection.signal_subscribe(
        BUS, REQUEST, "Response", path, None, Gio.DBusSignalFlags.NONE, on_response
    )

    def on_timeout() -> bool:
        nonlocal timed_out
        timed_out = True
        loop.quit()
        return False

    timeout_id = GLib.timeout_add(timeout_ms, on_timeout)
    try:
        options = dict(arguments[-1])
        options["handle_token"] = GLib.Variant("s", token)
        signature = {
            "CreateSession": "(a{sv})",
            "SelectDevices": "(oa{sv})",
            "Start": "(osa{sv})",
        }[method]
        parameters = GLib.Variant(signature, (*arguments[:-1], options))
        returned = connection.call_sync(
            BUS,
            OBJECT,
            REMOTE,
            method,
            parameters,
            GLib.VariantType.new("(o)"),
            Gio.DBusCallFlags.NONE,
            timeout_ms,
            None,
        )
        if returned.unpack()[0] != path:
            raise RuntimeError("portal request path changed")
        if not response:
            loop.run()
        if not response or response[0][0] != 0:
            return None
        return response[0][1]
    finally:
        accepting = False
        if not timed_out:
            GLib.source_remove(timeout_id)
        connection.signal_unsubscribe(subscription)
        if not response:
            try:
                connection.call_sync(
                    BUS,
                    path,
                    REQUEST,
                    "Close",
                    None,
                    None,
                    Gio.DBusCallFlags.NONE,
                    200,
                    None,
                )
            except GLib.Error:
                pass


def _focused_identity() -> tuple[str, int] | None:
    try:
        completed = run_process(
            [
                "busctl",
                "--user",
                "--json=short",
                "call",
                SHELL,
                SHELL_OBJECT,
                SHELL_INTERFACE,
                "GetActiveWindow",
            ],
            capture_output=True,
            text=True,
            check=False,
            timeout=3,
        )
        payload = json.loads(completed.stdout)
    except OSError, subprocess.TimeoutExpired, json.JSONDecodeError:
        return None
    values = payload.get("data")
    if (
        completed.returncode
        or payload.get("type") != "su"
        or not isinstance(values, list)
        or len(values) != 2
    ):
        return None
    app_id, pid = values
    if not isinstance(app_id, str) or type(pid) is not int or pid <= 0:
        return None
    return app_id, pid


def _window_and_pointer() -> tuple[str, int, int, int, int, int, int, int] | None:
    """Read one focused-window frame and cursor position from GNOME."""
    try:
        completed = run_process(
            [
                "busctl",
                "--user",
                "--json=short",
                "call",
                SHELL,
                SHELL_OBJECT,
                SHELL_INTERFACE,
                "GetActiveWindowAndPointer",
            ],
            capture_output=True,
            text=True,
            check=False,
            timeout=3,
        )
        payload = json.loads(completed.stdout)
    except OSError, subprocess.TimeoutExpired, json.JSONDecodeError:
        return None
    values = payload.get("data")
    if (
        completed.returncode
        or payload.get("type") != "suiiiiii"
        or not isinstance(values, list)
        or len(values) != 8
        or not isinstance(values[0], str)
        or any(type(value) is not int for value in values[1:])
    ):
        return None
    return (
        values[0],
        values[1],
        values[2],
        values[3],
        values[4],
        values[5],
        values[6],
        values[7],
    )


def _focused_window_token() -> str | None:
    return read_active_window_token(run=run_process)


def _capture_still_current(
    capture_id: str, regions: tuple[Rect, ...] | None = None
) -> bool:
    """Compare target evidence; absent evidence retains strict whole-image checks."""
    arguments = (
        ["ValidateCapture", "s", capture_id]
        if regions is None
        else [
            "ValidateCaptureRegions",
            "sa(iiii)",
            capture_id,
            str(len(regions)),
            *(str(value) for rect in regions for value in rect),
        ]
    )
    status = probe_gnome(
        "WindowCapturePrototype",
        {arguments[0], "capture-geometry-v1"},
        run=run_process,
    )
    if not status.ready:
        raise BackendUnavailable(status)
    try:
        completed = run_process(
            [
                "busctl",
                "--user",
                "--json=short",
                "call",
                SHELL,
                SCREEN_OBJECT,
                SCREEN_INTERFACE,
                *arguments,
            ],
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
        payload = json.loads(completed.stdout)
    except OSError, subprocess.TimeoutExpired, json.JSONDecodeError:
        return False
    return (
        completed.returncode == 0
        and payload.get("type") == "b"
        and payload.get("data") == [True]
    )


def _wait_for_expected_focus(expected: tuple[str, int], timeout_s: float = 10) -> bool:
    """Proceed promptly after the portal closes, but only for stable Telegram focus."""
    deadline = monotonic() + timeout_s
    while monotonic() < deadline:
        if _focused_identity() == expected:
            sleep(0.15)
            if _focused_identity() == expected:
                return True
        sleep(min(0.2, max(0.0, deadline - monotonic())))
    return False


def _key(
    connection: Gio.DBusConnection, session: str, symbol: int, pressed: bool
) -> None:
    connection.call_sync(
        BUS,
        OBJECT,
        REMOTE,
        "NotifyKeyboardKeysym",
        GLib.Variant("(oa{sv}iu)", (session, {}, symbol, 1 if pressed else 0)),
        None,
        Gio.DBusCallFlags.NONE,
        3000,
        None,
    )


def _press(connection: Gio.DBusConnection, session: str, symbol: int) -> None:
    _key(connection, session, symbol, True)
    try:
        sleep(0.02)
    finally:
        _key(connection, session, symbol, False)


def _atspi() -> Any:
    import gi  # type: ignore[import-not-found]

    try:
        gi.require_version("Atspi", "2.0")
        from gi.repository import Atspi
    except (ImportError, ValueError) as exc:
        raise ControlUnavailable("Telegram accessibility unavailable") from exc
    return Atspi


class _LiveControl:
    """Bind the object, ancestry and geometry to one focused window token."""

    def __init__(
        self, expected: tuple[str, int], kind: str, window_token: str | None = None
    ) -> None:
        self.expected = expected
        self.kind = kind
        self.token = _focused_window_token()
        self.frame = _window_and_pointer()
        if (
            not self.token
            or self.frame is None
            or self.frame[:2] != expected
            or (window_token is not None and self.token != window_token)
        ):
            raise ControlUnavailable("Telegram window identity unavailable")
        self.atspi = _atspi()
        self.control = locate_control(self.atspi, expected[1], self.frame[2:6], kind)
        self.resolve()

    def resolve(self, *, focused: bool = False) -> TelegramControl:
        if _focused_identity() != self.expected:
            raise ControlUnavailable("Telegram focus changed")
        frame = _window_and_pointer()
        if (
            frame is None
            or self.frame is None
            or frame[:6] != self.frame[:6]
            or _focused_window_token() != self.token
        ):
            raise ControlUnavailable("Telegram window changed")
        fresh = locate_control(self.atspi, self.expected[1], frame[2:6], self.kind)
        if fresh != self.control:
            raise ControlUnavailable("Telegram field identity or layout changed")
        if focused and not fresh.node.get_state_set().contains(
            self.atspi.StateType.FOCUSED
        ):
            raise ControlUnavailable("Telegram search lost focus")
        # Bracket AT-SPI traversal with independent Shell identity observations.
        if (
            _focused_identity() != self.expected
            or _focused_window_token() != self.token
            or (after := _window_and_pointer()) is None
            or after[:6] != frame[:6]
        ):
            raise ControlUnavailable("Telegram window changed during resolution")
        return fresh


def _type_search_target(
    connection: HelperLifetime,
    session: str,
    target: str,
    expected: tuple[str, int] | None = None,
    *,
    window_token: str | None = None,
) -> None:
    if expected is None:
        raise ValueError("Telegram field identity required")
    if not 1 <= len(target) <= 64 or any(
        not (char.isalnum() or char in " -_.'@") for char in target
    ):
        raise ValueError("unsupported chat search characters")
    if _focused_identity() != expected:
        raise ControlUnavailable("Telegram focus changed before search")
    field = _focus_search(connection, session, expected, window_token=window_token)
    connection.check(input_event=True)
    node = field.resolve(focused=True).node
    connection.check(input_event=True)
    if not node.get_editable_text_iface().set_text_contents(""):
        raise ControlUnavailable("Telegram search clear failed")
    # Object-directed editing cannot spill into another field if focus changes
    # inside a transport call. Four-character batches keep cancellation bounded.
    for offset in range(0, len(target), 4):
        connection.check(input_event=True)
        node = field.resolve(focused=True).node
        if node.get_text_iface().get_text(0, -1) != target[:offset]:
            raise ControlUnavailable("Telegram search contents changed")
        chunk = target[offset : offset + 4]
        connection.check(input_event=True)
        if not node.get_editable_text_iface().insert_text(
            offset, chunk, len(chunk.encode("utf-8"))
        ):
            raise ControlUnavailable("Telegram search insert failed")
    connection.check()
    node = field.resolve(focused=True).node
    if node.get_text_iface().get_text(0, -1) != target:
        raise ControlUnavailable("Telegram search text unverified")


def _focus_search(
    connection: HelperLifetime,
    session: str,
    expected: tuple[str, int] | None = None,
    *,
    window_token: str | None = None,
) -> _LiveControl:
    if expected is None:
        raise ValueError("Telegram field identity required")
    # Preserve the owner-validated two-Escape global-search navigation. Every
    # press is bound to the initial window; search text uses no global keys.
    token = window_token or _focused_window_token()
    if not token:
        raise ControlUnavailable("Telegram window identity unavailable")
    for _ in range(2):
        connection.check(input_event=True)
        if _focused_identity() != expected or _focused_window_token() != token:
            raise ControlUnavailable("Telegram focus changed before search")
        _press(connection, session, ESCAPE)
        sleep(0.15)
    field = _LiveControl(expected, "search", token)
    if field.token != token:
        raise ControlUnavailable("Telegram search window changed")
    connection.check(input_event=True)
    node = field.resolve().node
    connection.check(input_event=True)
    if not node.get_component_iface().grab_focus():
        raise ControlUnavailable("Telegram search focus rejected")
    field.resolve(focused=True)
    return field


def _open_menu(
    connection: HelperLifetime,
    expected: tuple[str, int],
    *,
    window_token: str | None = None,
) -> bool:
    control = _LiveControl(expected, "menu", window_token)
    connection.check(input_event=True)
    node = control.resolve().node
    action = action_index(node, None)
    if action is None:
        raise ControlUnavailable("Telegram menu has no supported action")
    connection.check(input_event=True)
    control.resolve()
    connection.check(input_event=True)
    return bool(action[0].do_action(action[1]))


def _click_verified_box(
    connection: Gio.DBusConnection,
    session: str,
    expected: tuple[str, int],
    box: tuple[int, int, int, int, int, int],
    *,
    menu_item: bool = False,
    settings_item: bool = False,
    visible_row: bool = False,
    geometry: CaptureGeometry | None = None,
    evidence_regions: tuple[Rect, ...] | None = None,
) -> bool:
    left, top, width, height, image_width, image_height = box
    if (
        min(left, top, width, height, image_width, image_height) < 0
        or width == 0
        or height == 0
        or left + width > image_width
        or top + height > image_height
    ):
        return False
    if evidence_regions is not None and (
        geometry is None
        or (left, top, width, height) not in evidence_regions
        or not capture_regions_valid(evidence_regions, (image_width, image_height))
    ):
        return False
    if settings_item:
        if (
            left < image_width * 0.02
            or left + width >= image_width * 0.9
            or not image_height * 0.06 < top < image_height * 0.86
        ):
            return False
    elif left + width >= image_width * 0.3 or not (
        image_height * (0.025 if menu_item else 0.07)
        < top
        < image_height * (0.98 if visible_row else 0.75)
    ):
        return False
    before = _window_and_pointer()
    if before is None or before[:2] != expected:
        return False
    app_id, pid, frame_x, frame_y, frame_w, frame_h, pointer_x, pointer_y = before
    if geometry is not None:
        if not capture_is_current(geometry, _focused_window_token(), monotonic()):
            return False
        if not _capture_still_current(geometry.capture_id, evidence_regions):
            return False
        if geometry.viewport_rect != (
            frame_x,
            frame_y,
            frame_w,
            frame_h,
        ) or geometry.image_size != (image_width, image_height):
            return False
        point = coordinate_to_desktop(
            geometry,
            (left + width / 2, top + height / 2),
            image_pixels=True,
            target_box=(left, top, width, height),
        )
        if point is None:
            return False
        target_x, target_y = point
    else:
        if (frame_w, frame_h) != (image_width, image_height):
            return False
        target_x = frame_x + left + width // 2
        target_y = frame_y + top + height // 2
    if not (
        frame_x <= target_x < frame_x + frame_w
        and frame_y <= target_y < frame_y + frame_h
    ):
        return False
    connection.call_sync(
        BUS,
        OBJECT,
        REMOTE,
        "NotifyPointerMotion",
        GLib.Variant(
            "(oa{sv}dd)",
            (session, {}, float(target_x - pointer_x), float(target_y - pointer_y)),
        ),
        None,
        Gio.DBusCallFlags.NONE,
        3000,
        None,
    )
    sleep(0.1)
    after = _window_and_pointer()
    if (
        after is None
        or after[:6] != (app_id, pid, frame_x, frame_y, frame_w, frame_h)
        or abs(after[6] - target_x) > 5
        or abs(after[7] - target_y) > 5
    ):
        return False
    if after[6:] != (target_x, target_y):
        return False
    if geometry is not None and not capture_is_current(
        geometry, _focused_window_token(), monotonic()
    ):
        return False
    for state in (1, 0):
        connection.call_sync(
            BUS,
            OBJECT,
            REMOTE,
            "NotifyPointerButton",
            GLib.Variant("(oa{sv}iu)", (session, {}, LEFT_BUTTON, state)),
            None,
            Gio.DBusCallFlags.NONE,
            3000,
            None,
        )
    return True


def main() -> int:
    grant_modes = {("grant",), ("grant-control",)}
    if tuple(sys.argv[1:]) not in grant_modes:
        status = probe_gnome(
            "ActiveApp",
            {"GetActiveWindow", "GetActiveWindowToken", "GetActiveWindowAndPointer"},
            run=run_process,
        )
        if not status.ready:
            raise BackendUnavailable(status)
    argv = sys.argv
    evidence_regions = None
    evidence_args = [value for value in argv[1:] if value.startswith("evidence=")]
    if evidence_args:
        if len(evidence_args) != 1:
            raise ValueError("duplicate capture evidence")
        data = json.loads(evidence_args[0].removeprefix("evidence="))
        if not isinstance(data, list) or not all(
            isinstance(rect, list) for rect in data
        ):
            raise ValueError("invalid capture evidence")
        evidence_regions = tuple(tuple(rect) for rect in data)
        argv = [value for value in argv if value != evidence_args[0]]
    grant_control = argv[1:] == ["grant-control"]
    if grant_control:
        mode = "grant-control"
        expected = None
    else:
        if len(argv) < 3:
            raise ValueError("expected Telegram desktop ID and PID")
        expected = (argv[1], int(argv[2]))
        mode = "saved" if len(argv) == 3 else argv[3]
    if mode not in {
        "saved",
        "search",
        "focus-search",
        "click",
        "visible-click",
        "menu-click",
        "settings-click",
        "escape",
        "grant-control",
        "view",
        "menu",
    }:
        raise ValueError("unsupported chat input mode")
    if not grant_control and (
        (mode == "saved" and len(argv) not in (3, 4))
        or (mode == "search" and len(argv) != 5)
        or (mode == "focus-search" and len(argv) != 4)
        or (
            mode in {"click", "visible-click", "menu-click", "settings-click"}
            and len(argv) not in {10, 11}
        )
        or (
            mode == "view"
            and (len(argv) != 5 or argv[4] not in {"archive", "contacts"})
        )
        or (mode in {"menu", "escape"} and len(argv) != 4)
    ):
        raise ValueError("invalid chat input arguments")
    if expected is not None:
        if "telegram" not in expected[0].casefold() or expected[1] <= 0:
            raise ValueError("expected identity must be Telegram")
        if _focused_identity() != expected:
            print("FOCUS_CHANGED", flush=True)
            return 2
    bound_mode = mode in {"menu", "search", "focus-search"}
    initial_window_token = _focused_window_token() if bound_mode else None
    acquired = shared_session(3)
    if acquired is None:
        print("CONTROL_SETUP_REQUIRED", flush=True)
        return 3
    connection, session = acquired
    if bound_mode and initial_window_token is None:
        connection.close()
        print("TARGET_CHANGED", flush=True)
        return 2
    try:
        print("INPUT_GRANTED focus_telegram_within=10s", flush=True)
        assert expected is not None
        if not _wait_for_expected_focus(expected):
            print("FOCUS_CHANGED", flush=True)
            return 2
        if mode == "saved":
            _key(connection, session, CONTROL, True)
            try:
                _press(connection, session, ZERO)
            finally:
                _key(connection, session, CONTROL, False)
            print("SHORTCUT_DISPATCHED", flush=True)
        elif mode == "search":
            _type_search_target(
                connection,
                session,
                argv[4],
                expected,
                window_token=initial_window_token,
            )
            print("SEARCH_TYPED", flush=True)
        elif mode == "focus-search":
            _focus_search(
                connection, session, expected, window_token=initial_window_token
            )
            print("SEARCH_FOCUSED", flush=True)
        elif mode == "view":
            _key(connection, session, CONTROL, True)
            try:
                _press(connection, session, NINE if argv[4] == "archive" else J_KEY)
            finally:
                _key(connection, session, CONTROL, False)
            print("VIEW_SHORTCUT_DISPATCHED", flush=True)
        elif mode == "escape":
            if _focused_identity() != expected:
                print("FOCUS_CHANGED", flush=True)
                return 2
            _press(connection, session, ESCAPE)
            print("ESCAPE_DISPATCHED", flush=True)
        elif mode == "menu":
            if not _open_menu(connection, expected, window_token=initial_window_token):
                print("TARGET_CHANGED", flush=True)
                return 2
            print("MENU_CLICKED", flush=True)
        else:
            geometry = (
                CaptureGeometry.from_json(argv[10].removeprefix("geometry="))
                if len(argv) == 11 and argv[10].startswith("geometry=")
                else None
            )
            if len(argv) == 11 and geometry is None:
                raise ValueError("invalid capture geometry")
            box = (
                int(argv[4]),
                int(argv[5]),
                int(argv[6]),
                int(argv[7]),
                int(argv[8]),
                int(argv[9]),
            )
            clicked = _click_verified_box(
                connection,
                session,
                expected,
                box,
                menu_item=mode == "menu-click",
                settings_item=mode == "settings-click",
                visible_row=mode == "visible-click",
                geometry=geometry,
                evidence_regions=evidence_regions,
            )
            if not clicked:
                print("TARGET_CHANGED", flush=True)
                return 2
            marker = (
                "SETTING_CLICKED" if mode == "settings-click" else "CHAT_RESULT_CLICKED"
            )
            print(marker, flush=True)
        return 0
    except ControlUnavailable:
        print("TARGET_CHANGED", flush=True)
        return 2
    finally:
        connection.close()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except BackendUnavailable as exc:
        print("BACKEND_UNAVAILABLE:" + exc.status.reason, flush=True)
        raise SystemExit(1) from exc
    except (GLib.Error, RuntimeError, ValueError, KeyError, TypeError) as exc:
        print(f"Keyboard action unavailable: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
