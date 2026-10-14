"""One-shot Telegram Saved Messages shortcut with remembered portal consent.

This diagnostic never sends text or pointer input. Run with system Python so
Ubuntu's Gio bindings are available. It closes the remote-desktop session on
every exit path and reports only whether the fixed shortcut was dispatched.
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
ZERO = ord("0")
TOKEN_PATH = permission_token_path("telegram-keyboard")


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


def main() -> int:
    if len(sys.argv) != 3:
        raise ValueError("expected Telegram desktop ID and PID")
    expected = (sys.argv[1], int(sys.argv[2]))
    if "telegram" not in expected[0].casefold() or expected[1] <= 0:
        raise ValueError("expected identity must be Telegram")
    if _focused_identity() != expected:
        print("FOCUS_CHANGED", flush=True)
        return 2
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
            return 1
        session = created["session_handle"]
        remembered = read_opaque_token(TOKEN_PATH)
        options = {"types": GLib.Variant("u", 1), "persist_mode": GLib.Variant("u", 2)}
        if remembered is not None:
            options["restore_token"] = GLib.Variant("s", remembered)
        selected = _request(
            connection,
            "SelectDevices",
            (session, options),
            8000,
        )
        if selected is None:
            return 1
        started = _request(connection, "Start", (session, "", {}), 30000)
        if started is None or started.get("devices", 0) & 1 == 0:
            return 1
        replacement = started.get("restore_token")
        if isinstance(replacement, str):
            try:
                save_opaque_token(TOKEN_PATH, replacement)
            except (OSError, ValueError) as exc:
                print(f"Could not remember keyboard permission: {exc}", file=sys.stderr)
        elif remembered is not None:
            # An old restore token may have been consumed. Never reuse it.
            try:
                TOKEN_PATH.unlink(missing_ok=True)
            except OSError as exc:
                print(
                    f"Could not clear old keyboard permission: {exc}",
                    file=sys.stderr,
                )
        print("KEYBOARD_GRANTED focus_telegram_within=10s", flush=True)
        if not _wait_for_expected_focus(expected):
            print("FOCUS_CHANGED", flush=True)
            return 2
        _key(connection, session, CONTROL, True)
        try:
            _key(connection, session, ZERO, True)
            try:
                sleep(0.05)
            finally:
                _key(connection, session, ZERO, False)
        finally:
            _key(connection, session, CONTROL, False)
        print("SHORTCUT_DISPATCHED", flush=True)
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
