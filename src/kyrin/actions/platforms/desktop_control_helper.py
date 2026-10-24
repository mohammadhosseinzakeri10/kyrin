"""One focused-window action with a separate desktop-control grant.

AT-SPI Action needs no screenshot or portal connection. Coordinate fallback
uses RemoteDesktop and rechecks focus, geometry, node state and pointer motion.
"""

import json
import sys
from pathlib import Path
from time import monotonic, sleep
from typing import Any
from uuid import uuid4

# A read-only handshake must not import GI or open a desktop connection.
if __name__ == "__main__" and sys.argv[1:] == ["--capabilities"]:
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
    from kyrin.backend_protocol import helper_manifest

    print(helper_manifest("desktop_control-v1"))
    raise SystemExit(0)

from gi.repository import Gio, GLib  # type: ignore[import-not-found]

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from kyrin.actions.platforms.desktop_accessibility import (  # noqa: E402
    Control,
    ControlUnavailable,
    action_index,
    active_accessible_window,
    resolve_control,
    valid_node,
)
from kyrin.actions.platforms.helper_lifecycle import HelperLifetime  # noqa: E402
from kyrin.actions.platforms.telegram_portal_helper import (  # noqa: E402
    BUS,
    LEFT_BUTTON,
    OBJECT,
    REMOTE,
    SESSION,
    _capture_still_current,
    _focused_identity,
    _focused_window_token,
    _request,
    _wait_for_expected_focus,
    _window_and_pointer,
)
from kyrin.app.permission_token import (  # noqa: E402
    permission_token_path,
    read_opaque_token,
)
from kyrin.backend_protocol import BackendUnavailable, probe_gnome  # noqa: E402
from kyrin.desktop.accessibility_target import AccessibilityTarget
from kyrin.desktop.window_observation import WindowObservation  # noqa: E402
from kyrin.operations import run_process  # noqa: E402
from kyrin.vision.capture_geometry import (  # noqa: E402
    MAX_CAPTURE_AGE_S,
    CaptureGeometry,
    capture_is_current,
    coordinate_to_desktop,
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
    target: AccessibilityTarget | None = None,
) -> Control | None:
    """Coordinate fallback only for a valid control without Action."""
    atspi = _atspi()
    control = resolve_control(atspi.get_desktop(0), pid, atspi, frame, label, target)
    if control is None:
        return None
    node, _target, _valid, checked, point = control
    if point is None or (state_required and checked is None):
        return None
    if action_index(node, True if state_required else None) is not None:
        raise ControlUnavailable("coordinate fallback cannot replace an action")
    x, y = point
    if near is not None and (
        abs(x - near[0]) > (24 if strict_near else 320) or abs(y - near[1]) > 24
    ):
        raise ControlUnavailable("control is not at the observed anchor")
    return control


def _atspi() -> Any:
    import gi  # type: ignore[import-not-found]

    gi.require_version("Atspi", "2.0")
    from gi.repository import Atspi

    return Atspi


def _semantic_control(
    expected: tuple[str, int],
    label: str,
    desired: bool | None,
    observation: WindowObservation,
    lifetime: HelperLifetime,
    target: AccessibilityTarget | None = None,
    consent: tuple[int, int, bool | None] | None = None,
) -> str:
    """Invoke one actual Action, without screenshot or RemoteDesktop setup."""

    def evidence() -> bool:
        return (
            observation.identity == expected
            and observation.current(_focused_window_token(), monotonic())
            and _focused_identity() == expected
        )

    if not evidence():
        return "TARGET_CHANGED:stale_or_window"
    frame = _window_and_pointer()
    if frame is None or frame[:2] != expected:
        return "FOCUS_CHANGED"
    atspi = _atspi()
    desktop = atspi.get_desktop(0)
    control = resolve_control(desktop, expected[1], atspi, frame[2:6], label, target)
    if control is None:
        return (
            "NO_ACCESSIBLE_ACTION" if evidence() else "TARGET_CHANGED:stale_or_window"
        )
    node, structural_target, _valid, checked, _point = control
    if not _matches_consent(control, frame[2:6], consent):
        return "TARGET_UNCERTAIN"
    if desired is not None and checked is None:
        return "STATE_UNAVAILABLE"
    if desired is not None and checked == desired:
        return "STATE_ALREADY_SET" if evidence() else "TARGET_CHANGED:stale_or_window"
    selected = action_index(node, desired)
    if selected is None:
        return (
            "NO_ACCESSIBLE_ACTION" if evidence() else "TARGET_CHANGED:stale_or_window"
        )
    # Re-resolve the same object/role/ancestry after capability reads. Never
    # substitute another same-named control or blindly reuse an action index.
    fresh = resolve_control(
        desktop, expected[1], atspi, frame[2:6], label, structural_target
    )
    if (
        fresh is None
        or fresh[0] != node
        or action_index(node, desired) != selected
        or not _matches_consent(fresh, frame[2:6], consent)
    ):
        return "TARGET_UNCERTAIN"
    if desired is not None and fresh[3] != checked:
        return "TARGET_UNCERTAIN"
    final_frame = _window_and_pointer()
    if not evidence() or final_frame is None or final_frame[:6] != frame[:6]:
        return "TARGET_CHANGED:stale_or_window"
    lifetime.check(input_event=True)
    fresh = resolve_control(
        desktop, expected[1], atspi, frame[2:6], label, structural_target
    )
    if (
        fresh is None
        or fresh[0] != node
        or action_index(node, desired) != selected
        or not _matches_consent(fresh, frame[2:6], consent)
        or (desired is not None and fresh[3] != checked)
    ):
        return "TARGET_UNCERTAIN"
    lifetime.check()
    if not evidence():
        return "TARGET_CHANGED:stale_or_window"
    action, index = selected
    try:
        invoked = action.do_action(index)
    except GLib.Error, ControlUnavailable, AttributeError, TypeError:
        invoked = False
    # Even a false/uncertain reply can follow a real state change. Observe before
    # considering recovery; this path never retries Action or falls back to input.
    confirmed = _control_postcondition(
        expected,
        label,
        desired,
        observation,
        structural_target,
        lifetime,
        expected_node=node,
    )
    return confirmed or ("ACTION_DISPATCHED" if invoked else "ACTION_UNCONFIRMED")


def _navigation_confirmed(
    expected: tuple[str, int], label: str, previous_token: str
) -> bool:
    """Only an exact active dialog title proves generic navigation.

    A new node, a changed image or the original button's label is insufficient.
    Unexported pages and dialogs with different titles stay unverified.
    """
    try:
        token = _focused_window_token()
        if token is None or token == previous_token or _focused_identity() != expected:
            return False
        atspi = _atspi()
        desktop = atspi.get_desktop(0)
        desktop.clear_cache()
        window = active_accessible_window(desktop, expected[1], atspi)
        return (
            window is not None
            and window.get_role() == atspi.Role.DIALOG
            and valid_node(window, atspi)
            and " ".join(window.get_name().casefold().split())
            == " ".join(label.casefold().split())
            and _focused_window_token() == token
            and _focused_identity() == expected
        )
    except ImportError, GLib.Error, ControlUnavailable, AttributeError, TypeError:
        return False


def _control_postcondition(
    expected: tuple[str, int],
    label: str,
    desired: bool | None,
    observation: WindowObservation | None,
    target: AccessibilityTarget | None,
    lifetime: HelperLifetime | None = None,
    *,
    expected_node: Any = None,
) -> str | None:
    """Bounded read-only settling inside the original observation/operation budget."""
    if observation is None:
        return None
    deadline = min(observation.deadline, monotonic() + 0.3)
    for attempt in range(7):
        if lifetime is not None:
            lifetime.check()
        if monotonic() >= deadline or _focused_identity() != expected:
            return None
        if desired is None:
            if _navigation_confirmed(expected, label, observation.window_token) and (
                monotonic() < deadline
            ):
                return "NAVIGATION_CONFIRMED"
        else:
            if not observation.current(_focused_window_token(), monotonic()):
                return None
            frame = _window_and_pointer()
            if frame is None or frame[:2] != expected:
                return None
            try:
                atspi = _atspi()
                fresh = resolve_control(
                    atspi.get_desktop(0), expected[1], atspi, frame[2:6], label, target
                )
                if (
                    fresh is not None
                    and fresh[0] == expected_node
                    and fresh[3] == desired
                ):
                    if (
                        observation.current(_focused_window_token(), monotonic())
                        and (_focused_identity() == expected)
                        and monotonic() < deadline
                    ):
                        return "STATE_CONFIRMED"
            except (
                ImportError,
                GLib.Error,
                ControlUnavailable,
                AttributeError,
                TypeError,
            ):
                return None
        if attempt < 6:
            sleep(min(0.05, max(0, deadline - monotonic())))
    return None


def _click(
    connection: Gio.DBusConnection,
    session: str,
    expected: tuple[str, int],
    box: tuple[int, int, int, int, int, int],
    label: str,
    desired: bool | None,
    accessible_only: bool,
    anchor: tuple[int, int] | None,
    capture_geometry: (
        CaptureGeometry | tuple[int, int, int, int, int, int, int, int] | None
    ) = None,
    observation: WindowObservation | None = None,
    accessibility_target: AccessibilityTarget | None = None,
    consent: tuple[int, int, bool | None] | None = None,
) -> str:
    def evidence_error() -> str | None:
        if observation is not None and not observation.current(
            observation.window_token, monotonic()
        ):
            return "TARGET_CHANGED:stale_capture"
        if isinstance(capture_geometry, CaptureGeometry) and not (
            0 <= monotonic() - capture_geometry.captured_at <= MAX_CAPTURE_AGE_S
        ):
            return "TARGET_CHANGED:stale_capture"
        token = _focused_window_token()
        if observation is not None:
            if observation.identity != expected or token != observation.window_token:
                return "TARGET_CHANGED:window_token"
            if not observation.current(token, monotonic()):
                return "TARGET_CHANGED:stale_capture"
        if isinstance(capture_geometry, CaptureGeometry):
            if token != capture_geometry.window_token:
                return "TARGET_CHANGED:window_token"
            if not capture_is_current(capture_geometry, token, monotonic()):
                return "TARGET_CHANGED:stale_capture"
        return None

    if observation is not None or isinstance(capture_geometry, CaptureGeometry):
        error = evidence_error()
        if error is not None:
            return error
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
    if not accessible_only and isinstance(capture_geometry, CaptureGeometry):
        if not 0 <= monotonic() - capture_geometry.captured_at <= MAX_CAPTURE_AGE_S:
            return "TARGET_CHANGED:stale_capture"
        if _focused_window_token() != capture_geometry.window_token:
            return "TARGET_CHANGED:window_token"
        if not _capture_still_current(
            capture_geometry.capture_id, ((left, top, width, height),)
        ):
            return "TARGET_CHANGED:content"
        if capture_geometry.viewport_rect != (frame_x, frame_y, frame_w, frame_h):
            return "TARGET_CHANGED:frame_size"
        if capture_geometry.image_size != (image_width, image_height):
            return "TARGET_UNCERTAIN"
        point = coordinate_to_desktop(
            capture_geometry,
            (left + width / 2, top + height / 2),
            image_pixels=True,
            target_box=(left, top, width, height),
        )
        if point is None:
            return "TARGET_UNCERTAIN"
        x, y = point
    elif not accessible_only and isinstance(capture_geometry, tuple):
        capture_x, capture_y, capture_w, capture_h, *captured_frame = capture_geometry
        if (frame_x, frame_y, frame_w, frame_h) != tuple(captured_frame):
            return "TARGET_CHANGED:frame_size"
        if (image_width, image_height) != (capture_w, capture_h):
            # Legacy rectangles do not locate shadow padding or establish the
            # PNG scale. Equal extra dimensions do not prove symmetric borders.
            return "CAPTURE_GEOMETRY_REQUIRED"
        x = capture_x + left + width // 2
        y = capture_y + top + height // 2
        if not (frame_x <= x < frame_x + frame_w and frame_y <= y < frame_y + frame_h):
            return "TARGET_UNCERTAIN"
    else:
        if not accessible_only and ((frame_w, frame_h) != (image_width, image_height)):
            return "CAPTURE_GEOMETRY_REQUIRED"
        x = frame_x + left + width // 2
        y = frame_y + top + height // 2
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
        target=accessibility_target,
    )
    if control is None and (desired is not None or accessible_only):
        return "STATE_UNAVAILABLE" if desired is not None else "TARGET_UNCERTAIN"
    if not _matches_consent(control, frame[2:6], consent):
        return "TARGET_UNCERTAIN"
    current = None
    if control is not None:
        _, accessibility_target, _valid, current, point = control
        assert point is not None
        if desired is not None or accessible_only:
            x, y = point
    if observation is not None or isinstance(capture_geometry, CaptureGeometry):
        error = evidence_error()
        if error is not None:
            return error
    if desired is not None and current == desired:
        return "STATE_ALREADY_SET"
    if observation is not None:
        error = evidence_error()
        if error is not None:
            return error
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
    final_frame = _window_and_pointer()
    if (
        final_frame is None
        or final_frame[:6] != frame[:6]
        or final_frame[6:] != (x, y)
        or not (frame_x <= x < frame_x + frame_w and frame_y <= y < frame_y + frame_h)
    ):
        return "TARGET_CHANGED:pointer_or_window"
    if isinstance(capture_geometry, CaptureGeometry) and not accessible_only:
        final_point = coordinate_to_desktop(
            capture_geometry,
            (left + width / 2, top + height / 2),
            image_pixels=True,
            target_box=(left, top, width, height),
        )
        if final_point != (x, y):
            return "TARGET_CHANGED:pointer_or_window"
        if not capture_is_current(
            capture_geometry, _focused_window_token(), monotonic()
        ):
            return "TARGET_CHANGED:stale_or_window"
    # Portal motion may yield long enough for a node to become hidden,
    # disabled or gain an Action. Revalidate the same ancestry before pressing.
    final_control = _accessible_control(
        label,
        (frame_x, frame_y, frame_w, frame_h),
        expected[1],
        near=(x, y),
        state_required=desired is not None,
        strict_near=True,
        target=accessibility_target,
    )
    if (control is None) != (final_control is None):
        return "TARGET_UNCERTAIN"
    if final_control is not None and (
        final_control[4] != (x, y) or final_control[3] != current
    ):
        return "TARGET_UNCERTAIN"
    for state in (1, 0):
        # Validate immediately before pressing; release an already pressed
        # button even when focus changes, to avoid leaving it held down.
        if state == 1 and (
            observation is not None or isinstance(capture_geometry, CaptureGeometry)
        ):
            error = evidence_error()
            if error is not None:
                return error
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
    return (
        _control_postcondition(
            expected,
            label,
            desired,
            observation,
            accessibility_target,
            expected_node=control[0] if control is not None else None,
        )
        or "CLICK_DISPATCHED"
    )


def _matches_consent(
    control: Control | None,
    frame: tuple[int, int, int, int],
    consent: tuple[int, int, bool | None] | None,
) -> bool:
    if consent is None:
        return True
    return (
        control is not None
        and control[3] is consent[2]
        and control[4] == (frame[0] + consent[0], frame[1] + consent[1])
    )


def _parse_consent(argv: list[str]) -> tuple[int, int, bool | None] | None:
    values = [
        arg.removeprefix("consent=") for arg in argv if arg.startswith("consent=")
    ]
    if not values:
        return None
    if len(values) != 1:
        raise ValueError("duplicate control consent")
    value = json.loads(values[0])
    if (
        not isinstance(value, list)
        or len(value) != 3
        or type(value[0]) is not int
        or type(value[1]) is not int
        or min(value[:2]) < 0
        or (value[2] is not None and type(value[2]) is not bool)
    ):
        raise ValueError("invalid control consent binding")
    return value[0], value[1], value[2]


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
    consent = _parse_consent(sys.argv)
    args = [arg for arg in sys.argv if not arg.startswith("consent=")]
    if len(args) >= 2 and args[1] == "semantic":
        if len(args) not in {7, 8}:
            raise ValueError("expected semantic identity, mode, label and observation")
        semantic_identity = (args[2], int(args[3]))
        semantic_desired = {"click": None, "on": True, "off": False}[args[4]]
        semantic_observation = WindowObservation.from_json(args[6])
        target = AccessibilityTarget.from_json(args[7]) if len(args) == 8 else None
        remembered = read_opaque_token(TOKEN_PATH)
        if remembered is None:
            print("CONTROL_SETUP_REQUIRED", flush=True)
            return 3
        lifetime = HelperLifetime(None, TOKEN_PATH, remembered)
        try:
            try:
                result = _semantic_control(
                    semantic_identity,
                    args[5],
                    semantic_desired,
                    semantic_observation,
                    lifetime,
                    target,
                    consent,
                )
            except (
                ControlUnavailable,
                GLib.Error,
                AttributeError,
                TypeError,
                ValueError,
            ):
                result = "TARGET_UNCERTAIN"
            print(result, flush=True)
            return (
                0
                if result
                in {
                    "ACTION_DISPATCHED",
                    "STATE_ALREADY_SET",
                    "STATE_CONFIRMED",
                    "NAVIGATION_CONFIRMED",
                    "NO_ACCESSIBLE_ACTION",
                }
                else 2
            )
        finally:
            lifetime.close()
    grant = sys.argv[1:] == ["grant"]
    observation_args = [arg for arg in sys.argv[1:] if arg.startswith("observation=")]
    observation = (
        WindowObservation.from_json(observation_args[0].removeprefix("observation="))
        if len(observation_args) == 1
        else None
    )
    if not grant and observation is None:
        print("TARGET_CHANGED:window_token", flush=True)
        return 2
    target_args = [arg for arg in sys.argv[1:] if arg.startswith("accessibility=")]
    accessibility_target = (
        AccessibilityTarget.from_json(target_args[0].removeprefix("accessibility="))
        if len(target_args) == 1
        else None
    )
    clean_argv = [
        arg
        for arg in sys.argv
        if not arg.startswith(("observation=", "accessibility=", "consent="))
    ]

    explicit = (
        CaptureGeometry.from_json(clean_argv[-1].removeprefix("geometry="))
        if not grant and clean_argv[-1].startswith("geometry=")
        else None
    )
    argv = clean_argv[:-1] if explicit is not None else clean_argv
    expected: tuple[str, int] | None = None
    box: tuple[int, int, int, int, int, int] | None = None
    label = ""
    desired: bool | None = None
    anchor: tuple[int, int] | None = None
    if not grant:
        if len(argv) not in {12, 14, 20, 22}:
            raise ValueError("expected identity, box, state and label")
        expected = (argv[1], int(argv[2]))
        box = tuple(int(part) for part in argv[3:9])  # type: ignore[assignment]
        desired = {"click": None, "on": True, "off": False}[argv[9]]
        label = argv[10]
        if len(argv) in {14, 22}:
            anchor = (int(argv[12]), int(argv[13]))
            if min(anchor) < 0:
                raise ValueError("invalid target anchor")
        capture_geometry = (
            tuple(int(value) for value in argv[14 if anchor else 12 :])
            if len(argv) in {20, 22}
            else None
        )
        if argv[11] not in {"visible", "accessible"} or expected[1] <= 0:
            raise ValueError("invalid control arguments")
        if _focused_identity() != expected:
            print("FOCUS_CHANGED", flush=True)
            return 2
    remembered = read_opaque_token(TOKEN_PATH)
    if not grant and remembered is None:
        print("CONTROL_SETUP_REQUIRED", flush=True)
        return 3
    connection = HelperLifetime(
        Gio.bus_get_sync(Gio.BusType.SESSION, None), TOKEN_PATH, remembered
    )
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
        connection.rotate(replacement)
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
            argv[11] == "accessible",
            anchor,
            explicit if explicit is not None else capture_geometry,  # type: ignore[arg-type]
            observation,
            accessibility_target,
            consent,
        )
        print(result, flush=True)
        return (
            0
            if result
            in {
                "CLICK_DISPATCHED",
                "STATE_ALREADY_SET",
                "STATE_CONFIRMED",
                "NAVIGATION_CONFIRMED",
            }
            else 2
        )
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
        connection.close()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except BackendUnavailable as exc:
        print("BACKEND_UNAVAILABLE:" + exc.status.reason, flush=True)
        raise SystemExit(1) from exc
    except (GLib.Error, RuntimeError, ValueError, OSError, KeyError, TypeError) as exc:
        print(f"Control unavailable: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
