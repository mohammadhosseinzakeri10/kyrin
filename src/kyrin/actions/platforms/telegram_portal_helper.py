"""One-shot Telegram chat input with remembered portal consent.

Only the search mode types a bounded chat name; it never presses Enter or
sends a message. Pointer mode clicks one OCR-approved search result after
fresh focus, geometry, and pointer-position checks. Run with system Python
for Ubuntu's Gio bindings. Every remote-desktop session is closed on exit.
"""

import json
import subprocess
import sys
from pathlib import Path
from time import monotonic, sleep
from typing import Any
from uuid import uuid4

from gi.repository import Gio, GLib  # type: ignore[import-not-found]

# This helper uses Ubuntu's system Python for GI even when KYRIN runs in a venv.
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from kyrin.app.permission_token import (  # noqa: E402
    permission_token_path,
    read_opaque_token,
    save_opaque_token,
)

BUS = "org.freedesktop.portal.Desktop"
OBJECT = "/org/freedesktop/portal/desktop"
REMOTE = "org.freedesktop.portal.RemoteDesktop"
REQUEST = "org.freedesktop.portal.Request"
SESSION = "org.freedesktop.portal.Session"
SHELL = "org.gnome.Shell"
SHELL_OBJECT = "/org/kyrin/ActiveApp"
SHELL_INTERFACE = "org.kyrin.ActiveApp"
CONTROL = 0xFFE3
ESCAPE = 0xFF1B
F_KEY = ord("f")
A_KEY = ord("a")
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
    token = "kyrin_" + uuid4().hex
    sender = connection.get_unique_name().replace(":", "").replace(".", "_")
    path = f"/org/freedesktop/portal/desktop/request/{sender}/{token}"
    loop = GLib.MainLoop()
    response: list[tuple[int, dict[str, Any]]] = []

    def on_response(_connection, _sender, _path, _interface, _signal, parameters):  # type: ignore[no-untyped-def]
        response.append(parameters.unpack())
        loop.quit()

    subscription = connection.signal_subscribe(
        BUS, REQUEST, "Response", path, None, Gio.DBusSignalFlags.NONE, on_response
    )
    timed_out = False

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
        loop.run()
        if not response or response[0][0] != 0:
            return None
        return response[0][1]
    finally:
        if not timed_out:
            GLib.source_remove(timeout_id)
        connection.signal_unsubscribe(subscription)


def _focused_identity() -> tuple[str, int] | None:
    try:
        completed = subprocess.run(
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
        completed = subprocess.run(
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


def _type_search_target(
    connection: Gio.DBusConnection,
    session: str,
    target: str,
    expected: tuple[str, int] | None = None,
) -> None:
    if not 1 <= len(target) <= 64 or any(
        not (char.isalnum() or char in " -_.'@") for char in target
    ):
        raise ValueError("unsupported chat search characters")
    _focus_search(connection, session, expected)
    _key(connection, session, CONTROL, True)
    try:
        _press(connection, session, A_KEY)
    finally:
        _key(connection, session, CONTROL, False)
    for char in target:
        codepoint = ord(char)
        symbol = codepoint if codepoint < 128 else 0x01000000 | codepoint
        _press(connection, session, symbol)


def _focus_search(
    connection: Gio.DBusConnection,
    session: str,
    expected: tuple[str, int] | None = None,
) -> None:
    """Exit a chat-specific search before focusing Telegram's global search."""
    # The first Escape closes an existing search; the second exits an open chat.
    # Ctrl+F can otherwise search only within that conversation.
    for _ in range(2):
        _press(connection, session, ESCAPE)
        sleep(0.15)
    if expected is not None and _focused_identity() != expected:
        raise ValueError("telegram focus changed before search")
    _key(connection, session, CONTROL, True)
    try:
        _press(connection, session, F_KEY)
    finally:
        _key(connection, session, CONTROL, False)


def _click_verified_box(
    connection: Gio.DBusConnection,
    session: str,
    expected: tuple[str, int],
    box: tuple[int, int, int, int, int, int],
    *,
    menu_button: bool = False,
    menu_item: bool = False,
    settings_item: bool = False,
    visible_row: bool = False,
) -> bool:
    left, top, width, height, image_width, image_height = box
    if (
        min(left, top, width, height, image_width, image_height) < 0
        or width == 0
        or height == 0
    ):
        return False
    if settings_item:
        if (
            left < image_width * 0.02
            or left + width >= image_width * 0.9
            or not image_height * 0.06 < top < image_height * 0.86
        ):
            return False
    elif (
        left + width >= image_width * 0.3
        or not (
            0 < top < image_height * 0.075
            if menu_button
            else image_height * (0.025 if menu_item else 0.07)
            < top
            < image_height * (0.98 if visible_row else 0.75)
        )
    ):
        return False
    before = _window_and_pointer()
    if before is None or before[:2] != expected:
        return False
    app_id, pid, frame_x, frame_y, frame_w, frame_h, pointer_x, pointer_y = before
    if abs(frame_w - image_width) > 4 or abs(frame_h - image_height) > 4:
        return False
    target_x = frame_x + left + width // 2
    target_y = frame_y + top + height // 2
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
    grant_control = sys.argv[1:] == ["grant-control"]
    if grant_control:
        mode = "grant-control"
        expected = None
    else:
        if len(sys.argv) < 3:
            raise ValueError("expected Telegram desktop ID and PID")
        expected = (sys.argv[1], int(sys.argv[2]))
        mode = "saved" if len(sys.argv) == 3 else sys.argv[3]
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
        (mode == "saved" and len(sys.argv) not in (3, 4))
        or (mode == "search" and len(sys.argv) != 5)
        or (mode == "focus-search" and len(sys.argv) != 4)
        or (
            mode in {"click", "visible-click", "menu-click", "settings-click"}
            and len(sys.argv) != 10
        )
        or (
            mode == "view"
            and (len(sys.argv) != 5 or sys.argv[4] not in {"archive", "contacts"})
        )
        or (mode in {"menu", "escape"} and len(sys.argv) != 4)
    ):
        raise ValueError("invalid chat input arguments")
    if expected is not None:
        if "telegram" not in expected[0].casefold() or expected[1] <= 0:
            raise ValueError("expected identity must be Telegram")
        if _focused_identity() != expected:
            print("FOCUS_CHANGED", flush=True)
            return 2
    device = 3  # One remembered RemoteDesktop grant covers keyboard and pointer.
    remembered = read_opaque_token(CONTROL_TOKEN_PATH)
    if mode != "grant-control" and remembered is None:
        print("CONTROL_SETUP_REQUIRED", flush=True)
        return 3
    connection = Gio.bus_get_sync(Gio.BusType.SESSION, None)
    session: str | None = None
    try:
        created = _request(
            connection,
            "CreateSession",
            ({"session_handle_token": GLib.Variant("s", "kyrin_" + uuid4().hex)},),
            8000,
        )
        if created is None:
            print("CONTROL_SESSION_UNAVAILABLE:create", flush=True)
            return 1
        session = created["session_handle"]
        options = {
            "types": GLib.Variant("u", device),
            "persist_mode": GLib.Variant("u", 2),
        }
        if remembered is not None:
            options["restore_token"] = GLib.Variant("s", remembered)
        selected = _request(
            connection,
            "SelectDevices",
            (session, options),
            8000,
        )
        if selected is None:
            print("CONTROL_SESSION_UNAVAILABLE:devices", flush=True)
            return 1
        started = _request(connection, "Start", (session, "", {}), 30000)
        if started is None or started.get("devices", 0) & device != device:
            print("CONTROL_SESSION_UNAVAILABLE:start", flush=True)
            return 1
        replacement = started.get("restore_token")
        stored = False
        if isinstance(replacement, str):
            try:
                save_opaque_token(CONTROL_TOKEN_PATH, replacement)
                stored = True
            except (OSError, ValueError) as exc:
                print(
                    f"Could not remember Telegram input permission: {exc}",
                    file=sys.stderr,
                )
        elif remembered is not None:
            # An old restore token may have been consumed. Never reuse it.
            try:
                CONTROL_TOKEN_PATH.unlink(missing_ok=True)
            except OSError as exc:
                print(
                    f"Could not clear old Telegram input permission: {exc}",
                    file=sys.stderr,
                )
        if mode == "grant-control":
            if not stored:
                return 1
            print("CONTROL_GRANT_READY", flush=True)
            return 0
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
            _type_search_target(connection, session, sys.argv[4], expected)
            print("SEARCH_TYPED", flush=True)
        elif mode == "focus-search":
            _focus_search(connection, session, expected)
            print("SEARCH_FOCUSED", flush=True)
        elif mode == "view":
            _key(connection, session, CONTROL, True)
            try:
                _press(connection, session, NINE if sys.argv[4] == "archive" else J_KEY)
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
            frame = _window_and_pointer()
            if (
                frame is None
                or frame[:2] != expected
                or frame[4] < 300
                or frame[5] < 300
            ):
                print("TARGET_CHANGED", flush=True)
                return 2
            # Telegram Desktop's hamburger is confined to this top-left box.
            box = (14, 26, 28, 32, frame[4], frame[5])
            if not _click_verified_box(
                connection, session, expected, box, menu_button=True
            ):
                print("TARGET_CHANGED", flush=True)
                return 2
            print("MENU_CLICKED", flush=True)
        else:
            box = (
                int(sys.argv[4]),
                int(sys.argv[5]),
                int(sys.argv[6]),
                int(sys.argv[7]),
                int(sys.argv[8]),
                int(sys.argv[9]),
            )
            clicked = _click_verified_box(
                connection,
                session,
                expected,
                box,
                menu_item=mode == "menu-click",
                settings_item=mode == "settings-click",
                visible_row=mode == "visible-click",
            )
            if not clicked:
                print("TARGET_CHANGED", flush=True)
                return 2
            marker = (
                "SETTING_CLICKED"
                if mode == "settings-click"
                else "CHAT_RESULT_CLICKED"
            )
            print(marker, flush=True)
        return 0
    finally:
        if session is not None:
            try:
                connection.call_sync(
                    BUS,
                    session,
                    SESSION,
                    "Close",
                    None,
                    None,
                    Gio.DBusCallFlags.NONE,
                    3000,
                    None,
                )
            except GLib.Error:
                pass


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (GLib.Error, RuntimeError, ValueError, KeyError, TypeError) as exc:
        print(f"Keyboard action unavailable: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
