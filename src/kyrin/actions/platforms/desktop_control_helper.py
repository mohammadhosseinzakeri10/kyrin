"""One focused-window click with a separate remembered desktop-control grant.

Runs with Ubuntu's system Python for Gio/AT-SPI. OCR coordinates are only a
proposal: focus, frame size and pointer movement are checked again here.
"""

import sys
from pathlib import Path
from time import monotonic, sleep
from uuid import uuid4

from gi.repository import Gio, GLib  # type: ignore[import-not-found]

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from kyrin.actions.platforms.telegram_portal_helper import (  # noqa: E402
    BUS,
    LEFT_BUTTON,
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

TOKEN_PATH = permission_token_path("desktop-control")


def _wait_for_pointer(
    frame: tuple[str, int, int, int, int, int, int, int],
    x: int,
    y: int,
    *,
    timeout_s: float = 0.3,
) -> bool:
    """Wait briefly for asynchronous portal motion, without trusting a moved window."""
    deadline = monotonic() + timeout_s
    while True:
        after = _window_and_pointer()
        if after is None or after[:6] != frame[:6]:
            return False
        if abs(after[6] - x) <= 5 and abs(after[7] - y) <= 5:
            return _focused_identity() == frame[:2]
        if monotonic() >= deadline:
            return False
        sleep(min(0.05, max(0.0, deadline - monotonic())))


def _accessible_control(
    label: str,
    frame: tuple[int, int, int, int],
    pid: int,
    *,
    near: tuple[int, int] | None,
    state_required: bool,
    strict_near: bool = False,
) -> tuple[bool | None, int, int] | None:
    """Locate one named actionable node in the focused app."""
    import gi  # type: ignore[import-not-found]

    gi.require_version("Atspi", "2.0")
    from gi.repository import Atspi

    normalized = " ".join(label.casefold().split())
    desktop = Atspi.get_desktop(0)
    found: list[tuple[bool | None, int, int]] = []
    queue = []
    for index in range(desktop.get_child_count()):
        app = desktop.get_child_at_index(index)
        try:
            if app.get_process_id() == pid:
                queue.append(app)
        except GLib.Error, TypeError, ValueError, AttributeError:
            continue
    inspected = 0
    state_roles = {
        Atspi.Role.CHECK_BOX,
        Atspi.Role.CHECK_MENU_ITEM,
        Atspi.Role.SWITCH,
        Atspi.Role.TOGGLE_BUTTON,
    }
    click_roles = state_roles | {
        Atspi.Role.BUTTON,
        Atspi.Role.ICON,
        Atspi.Role.LINK,
        Atspi.Role.MENU_ITEM,
        Atspi.Role.PUSH_BUTTON_MENU,
        Atspi.Role.RADIO_BUTTON,
        Atspi.Role.RADIO_MENU_ITEM,
    }
    while queue and inspected < 3000:
        node = queue.pop(0)
        inspected += 1
        try:
            if (
                node.get_role() in (state_roles if state_required else click_roles)
                and " ".join(node.get_name().casefold().split()) == normalized
            ):
                component = node.get_component()
                if component is not None:
                    rect = component.get_extents(Atspi.CoordType.SCREEN)
                    frame_x, frame_y, frame_w, frame_h = frame
                    control_x = rect.x + rect.width // 2
                    control_y = rect.y + rect.height // 2
                    if (
                        (
                            near is None
                            or (
                                abs(control_x - near[0]) <= (24 if strict_near else 320)
                                and abs(control_y - near[1]) <= 24
                            )
                        )
                        and frame_x <= control_x < frame_x + frame_w
                        and frame_y <= control_y < frame_y + frame_h
                    ):
                        state = node.get_state_set()
                        if state.contains(Atspi.StateType.ENABLED):
                            found.append(
                                (
                                    state.contains(Atspi.StateType.CHECKED)
                                    if node.get_role() in state_roles
                                    else None,
                                    control_x,
                                    control_y,
                                )
                            )
            count = min(node.get_child_count(), 200)
            queue.extend(node.get_child_at_index(i) for i in range(count))
        except GLib.Error, TypeError, ValueError, AttributeError:
            continue
    return found[0] if len(found) == 1 else None


def _click(
    connection: Gio.DBusConnection,
    session: str,
    expected: tuple[str, int],
    box: tuple[int, int, int, int, int, int],
    label: str,
    desired: bool | None,
    accessible_only: bool,
    anchor: tuple[int, int] | None,
    capture_geometry: tuple[int, int, int, int, int, int, int, int] | None = None,
) -> str:
    left, top, width, height, image_width, image_height = box
    if not accessible_only and (
        min(box) < 0
        or width < 2
        or height < 2
        or left + width > image_width
        or top + height > image_height
    ):
        return "TARGET_UNCERTAIN"
    frame = _window_and_pointer()
    if frame is None or frame[:2] != expected:
        return "FOCUS_CHANGED"
    _, _, frame_x, frame_y, frame_w, frame_h, pointer_x, pointer_y = frame
    if not accessible_only and capture_geometry is not None:
        capture_x, capture_y, capture_w, capture_h, *captured_frame = capture_geometry
        if (frame_x, frame_y, frame_w, frame_h) != tuple(captured_frame):
            return "TARGET_CHANGED:frame_size"
        extra_w = image_width - capture_w
        extra_h = image_height - capture_h
        symmetric_shadow = (
            (capture_x, capture_y, capture_w, capture_h)
            == (frame_x, frame_y, frame_w, frame_h)
            and 0 < extra_w == extra_h <= 128
            and extra_w % 2 == 0
        )
        if symmetric_shadow:
            # GNOME's window PNG can include the drop shadow while its area
            # describes only the frame. The extra border is on every side.
            x = capture_x + left + width // 2 - extra_w // 2
            y = capture_y + top + height // 2 - extra_h // 2
        elif (
            abs(extra_w) <= max(4, capture_w // 50)
            and abs(extra_h) <= max(4, capture_h // 50)
        ):
            x = capture_x + round((left + width / 2) * capture_w / image_width)
            y = capture_y + round((top + height / 2) * capture_h / image_height)
        else:
            return (
                "TARGET_CHANGED:image_scale_"
                f"{capture_w}x{capture_h}_png_{image_width}x{image_height}"
            )
        if not (frame_x <= x < frame_x + frame_w and frame_y <= y < frame_y + frame_h):
            return "TARGET_UNCERTAIN"
    else:
        if not accessible_only and (
            abs(frame_w - image_width) > 4 or abs(frame_h - image_height) > 4
        ):
            return "CAPTURE_GEOMETRY_REQUIRED"
        x = frame_x + left + width // 2
        y = frame_y + top + height // 2
    if desired is not None or accessible_only:
        control = _accessible_control(
            label,
            (frame_x, frame_y, frame_w, frame_h),
            expected[1],
            near=(
                (frame_x + anchor[0], frame_y + anchor[1])
                if anchor is not None
                else None
                if accessible_only
                else (x, y)
            ),
            state_required=desired is not None,
            strict_near=anchor is not None,
        )
        if control is None:
            return "STATE_UNAVAILABLE" if desired is not None else "TARGET_UNCERTAIN"
        current, x, y = control
        if desired is not None and current == desired:
            return "STATE_ALREADY_SET"
    connection.call_sync(
        BUS,
        OBJECT,
        REMOTE,
        "NotifyPointerMotion",
        GLib.Variant(
            "(oa{sv}dd)", (session, {}, float(x - pointer_x), float(y - pointer_y))
        ),
        None,
        Gio.DBusCallFlags.NONE,
        3000,
        None,
    )
    if not _wait_for_pointer(frame, x, y):
        return "TARGET_CHANGED:pointer_or_window"
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
    return "CLICK_DISPATCHED"


def main() -> int:
    grant = sys.argv[1:] == ["grant"]
    expected: tuple[str, int] | None = None
    box: tuple[int, int, int, int, int, int] | None = None
    label = ""
    desired: bool | None = None
    anchor: tuple[int, int] | None = None
    if not grant:
        if len(sys.argv) not in {12, 14, 20, 22}:
            raise ValueError("expected identity, box, state and label")
        expected = (sys.argv[1], int(sys.argv[2]))
        box = tuple(int(part) for part in sys.argv[3:9])  # type: ignore[assignment]
        desired = {"click": None, "on": True, "off": False}[sys.argv[9]]
        label = sys.argv[10]
        if len(sys.argv) in {14, 22}:
            anchor = (int(sys.argv[12]), int(sys.argv[13]))
            if min(anchor) < 0:
                raise ValueError("invalid target anchor")
        capture_geometry = (
            tuple(int(value) for value in sys.argv[14 if anchor else 12 :])
            if len(sys.argv) in {20, 22}
            else None
        )
        if sys.argv[11] not in {"visible", "accessible"} or expected[1] <= 0:
            raise ValueError("invalid control arguments")
        if _focused_identity() != expected:
            print("FOCUS_CHANGED", flush=True)
            return 2
    remembered = read_opaque_token(TOKEN_PATH)
    if not grant and remembered is None:
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
        options = {
            "types": GLib.Variant("u", 2),
            "persist_mode": GLib.Variant("u", 2),
        }
        if remembered is not None:
            options["restore_token"] = GLib.Variant("s", remembered)
        if _request(connection, "SelectDevices", (session, options), 8000) is None:
            return 1
        started = _request(connection, "Start", (session, "", {}), 30000)
        if started is None or started.get("devices", 0) & 2 != 2:
            return 1
        replacement = started.get("restore_token")
        if not isinstance(replacement, str):
            TOKEN_PATH.unlink(missing_ok=True)
            return 1
        save_opaque_token(TOKEN_PATH, replacement)
        if grant:
            print("CONTROL_GRANT_READY", flush=True)
            return 0
        assert expected is not None and box is not None
        if not _wait_for_expected_focus(expected):
            print("FOCUS_CHANGED", flush=True)
            return 2
        result = _click(
            connection,
            session,
            expected,
            box,
            label,
            desired,
            sys.argv[11] == "accessible",
            anchor,
            capture_geometry,  # type: ignore[arg-type]
        )
        print(result, flush=True)
        return 0 if result in {"CLICK_DISPATCHED", "STATE_ALREADY_SET"} else 2
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
        print(f"Control unavailable: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
