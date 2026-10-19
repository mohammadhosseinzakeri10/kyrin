"""Send one bounded scroll through a remembered RemoteDesktop pointer grant."""

import sys
from pathlib import Path
from time import sleep
from uuid import uuid4

from gi.repository import Gio, GLib  # type: ignore[import-not-found]

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from kyrin.actions.platforms.telegram_portal_helper import (  # noqa: E402
    BUS,
    OBJECT,
    REMOTE,
    SESSION,
    _focused_identity,
    _request,
    _wait_for_expected_focus,
    _window_and_pointer,
)
from kyrin.app.permission_token import (  # noqa: E402
    permission_token_path,
    read_opaque_token,
    save_opaque_token,
)


def _scroll(
    connection: Gio.DBusConnection,
    session: str,
    expected: tuple[str, int],
    *,
    direction: str,
    steps: int,
    left_pane: bool,
    smooth: bool,
    right_pane: bool = False,
) -> bool:
    frame = _window_and_pointer()
    if frame is None or frame[:2] != expected:
        return False
    _, _, frame_x, frame_y, width, height, pointer_x, pointer_y = frame
    if width < 300 or height < 200:
        return False
    target_x = frame_x + int(
        width * (0.65 if right_pane else 0.15 if left_pane else 0.5)
    )
    target_y = frame_y + int(height * 0.55)
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
    moved = _window_and_pointer()
    if (
        moved is None
        or moved[:6] != frame[:6]
        or abs(moved[6] - target_x) > 5
        or abs(moved[7] - target_y) > 5
        or _focused_identity() != expected
    ):
        return False
    if smooth:
        # A touchpad-style series produces a smaller, visible movement than
        # sending several wheel detents in one event.
        delta = 8.0 if direction == "down" else -8.0
        pulse_count = steps * 4
        for pulse in range(pulse_count):
            if _focused_identity() != expected:
                return False
            connection.call_sync(
                BUS,
                OBJECT,
                REMOTE,
                "NotifyPointerAxis",
                GLib.Variant(
                    "(oa{sv}dd)",
                    (
                        session,
                        {"finish": GLib.Variant("b", pulse == pulse_count - 1)},
                        0.0,
                        delta,
                    ),
                ),
                None,
                Gio.DBusCallFlags.NONE,
                3000,
                None,
            )
            if pulse < pulse_count - 1:
                sleep(0.04)
    else:
        signed_steps = steps if direction == "down" else -steps
        connection.call_sync(
            BUS,
            OBJECT,
            REMOTE,
            "NotifyPointerAxisDiscrete",
            GLib.Variant("(oa{sv}ui)", (session, {}, 0, signed_steps)),
            None,
            Gio.DBusCallFlags.NONE,
            3000,
            None,
        )
    return _focused_identity() == expected


def main() -> int:
    if sys.argv[1:] == ["grant"]:
        mode = "grant"
        expected = None
        direction = "down"
        steps = 1
        left_pane = False
        right_pane = False
        token_name = "desktop-scroll"
    else:
        if len(sys.argv) != 7:
            raise ValueError("expected app ID, PID, direction, steps, area, token")
        _, app_id, pid_text, direction, steps_text, area, token_name = sys.argv
        if direction not in {"up", "down"} or area not in {
            "center", "left", "right"
        }:
            raise ValueError("invalid scroll direction or area")
        steps = int(steps_text)
        if not 1 <= steps <= 4:
            raise ValueError("scroll steps out of range")
        if token_name not in {"desktop-scroll", "telegram-control"}:
            raise ValueError("unsupported input token")
        if token_name == "telegram-control" and "telegram" not in app_id.casefold():
            raise ValueError("Telegram token requires Telegram focus")
        expected = (app_id, int(pid_text))
        if expected[1] <= 0 or _focused_identity() != expected:
            print("FOCUS_CHANGED", flush=True)
            return 2
        left_pane = area == "left"
        right_pane = area == "right"
        mode = "scroll"

    token_path = permission_token_path(token_name)
    remembered = read_opaque_token(token_path)
    if mode == "scroll" and remembered is None:
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
            return 1
        session = created["session_handle"]
        devices = 3 if token_name == "telegram-control" else 2
        options = {
            "types": GLib.Variant("u", devices),
            "persist_mode": GLib.Variant("u", 2),
        }
        if remembered is not None:
            options["restore_token"] = GLib.Variant("s", remembered)
        if _request(connection, "SelectDevices", (session, options), 8000) is None:
            return 1
        started = _request(connection, "Start", (session, "", {}), 30000)
        if started is None or started.get("devices", 0) & devices != devices:
            return 1
        replacement = started.get("restore_token")
        if not isinstance(replacement, str):
            token_path.unlink(missing_ok=True)
            return 1
        save_opaque_token(token_path, replacement)
        if mode == "grant":
            print("SCROLL_GRANT_READY", flush=True)
            return 0
        assert expected is not None and session is not None
        if not _wait_for_expected_focus(expected):
            print("FOCUS_CHANGED", flush=True)
            return 2
        if not _scroll(
            connection,
            session,
            expected,
            direction=direction,
            steps=steps,
            left_pane=left_pane,
            smooth=token_name == "desktop-scroll",
            right_pane=right_pane,
        ):
            print("SCROLL_UNCERTAIN", flush=True)
            return 2
        print("SCROLL_DISPATCHED", flush=True)
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
    except (GLib.Error, RuntimeError, ValueError, OSError, KeyError, TypeError) as exc:
        print(f"Scroll unavailable: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
