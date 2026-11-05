"""One opt-in Terminal chord; no popup activation or arbitrary keyboard input."""

from __future__ import annotations

import sys
from pathlib import Path
from time import monotonic
from typing import Any

if __name__ == "__main__" and sys.argv[1:] == ["--capabilities"]:
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
    from kyrin.backend_protocol import helper_manifest

    print(helper_manifest("terminal-tab-keyboard-v1"))
    raise SystemExit(0)

from gi.repository import Gio, GLib  # type: ignore[import-not-found]

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from kyrin.actions.platforms.desktop_accessibility import (  # noqa: E402
    ControlUnavailable,
    active_accessible_window,
    resolve_control,
)
from kyrin.actions.platforms.desktop_control_helper import _atspi  # noqa: E402
from kyrin.actions.platforms.helper_lifecycle import shared_session  # noqa: E402
from kyrin.actions.platforms.ptyxis_menu import (  # noqa: E402
    configured_tab_binding,
    shortcut,
)
from kyrin.actions.platforms.telegram_portal_helper import (  # noqa: E402
    BUS,
    OBJECT,
    REMOTE,
    _focused_identity,
    _focused_window_token,
    _window_and_pointer,
)
from kyrin.backend_protocol import BackendUnavailable, probe_gnome  # noqa: E402
from kyrin.desktop.accessibility_target import AccessibilityTarget  # noqa: E402
from kyrin.desktop.window_observation import WindowObservation  # noqa: E402
from kyrin.operations import OperationStopped, run_process  # noqa: E402

# Only this reviewed command exists. Settings validate meaning, never supply keys.
TAB_CHORD = (0xFFE3, 0xFFE1, 0x0074)  # Control_L, Shift_L, t


def _target(
    observation: WindowObservation,
    target: AccessibilityTarget | None = None,
) -> tuple[tuple[Any, ...], AccessibilityTarget]:
    if (
        observation.app_id != "org.gnome.Ptyxis.desktop"
        or _focused_identity() != observation.identity
        or not observation.current(_focused_window_token(), monotonic())
    ):
        raise ControlUnavailable("target changed")
    frame = _window_and_pointer()
    if frame is None or frame[:2] != observation.identity:
        raise ControlUnavailable("target changed")
    api = _atspi()
    desktop = api.get_desktop(0)
    window = active_accessible_window(desktop, observation.process_id, api)
    if (
        window is None
        or window.get_role() != api.Role.FRAME
        or window.get_state_set().contains(api.StateType.MODAL)
    ):
        raise ControlUnavailable("target changed")
    menu = resolve_control(
        desktop, observation.process_id, api, frame[2:6], "Main Menu", target
    )
    if menu is None:
        raise ControlUnavailable("target changed")
    parent = menu[0].get_parent()
    if parent is None:
        raise ControlUnavailable("target changed")
    parent.clear_cache()
    if (
        parent.get_child_count() != 1
        or parent.get_child_at_index(0) != menu[0]
        or parent.get_state_set().contains(api.StateType.EXPANDED)
    ):
        raise ControlUnavailable("menu not closed")
    if _focused_identity() != observation.identity or not observation.current(
        _focused_window_token(), monotonic()
    ):
        raise ControlUnavailable("target changed")
    return frame[:6], menu[1]


def _key(lifetime: Any, session: str, symbol: int, pressed: bool) -> None:
    # The caller authorizes every event before its final target check. Bypass a
    # second checkpoint here so no acknowledgement wait follows that check.
    lifetime.connection.call_sync(
        BUS,
        OBJECT,
        REMOTE,
        "NotifyKeyboardKeysym",
        GLib.Variant("(oa{sv}iu)", (session, {}, symbol, int(pressed))),
        None,
        Gio.DBusCallFlags.NONE,
        max(1, min(1000, int(lifetime.operation.remaining() * 1000))),
        None,
    )


def _tab(observation: WindowObservation, lifetime: Any, session: str) -> str:
    settings = Gio.Settings.new("org.gnome.Ptyxis.Shortcuts")
    keys = tuple(settings.props.settings_schema.list_keys())

    def binding_matches() -> bool:
        try:
            return configured_tab_binding(keys, settings.get_string) == shortcut(
                "<ctrl><shift>t"
            )
        except ControlUnavailable:
            return False

    try:
        if not binding_matches():
            return "TAB_ITEM:TERMINAL_TAB_SHORTCUT_UNSUPPORTED"
        frame, target = _target(observation)
    except ControlUnavailable as error:
        return (
            "TAB_MENU:TERMINAL_TAB_CLOSE_MENU"
            if str(error) == "menu not closed"
            else "TAB_ITEM:TARGET_CHANGED:stale_or_window"
        )
    held: list[int] = []
    result = "TAB_ITEM:ACTION_UNCONFIRMED"
    try:
        for symbol in TAB_CHORD:
            lifetime.check(input_event=True)
            if not binding_matches():
                return "TAB_ITEM:TERMINAL_TAB_SHORTCUT_UNSUPPORTED"
            if _target(observation, target)[0] != frame:
                return "TAB_ITEM:TARGET_CHANGED:stale_or_window"
            lifetime.check()
            # A transport error may follow delivered input: retain for cleanup.
            held.append(symbol)
            _key(lifetime, session, symbol, True)
        result = "TAB_ITEM:ACTION_DISPATCHED"
    except OperationStopped:
        raise
    except ControlUnavailable:
        result = "TAB_ITEM:TARGET_CHANGED:stale_or_window"
    except GLib.Error:
        result = "TAB_ITEM:ACTION_UNCONFIRMED"
    finally:
        for symbol in reversed(held):
            lifetime.check(input_event=True)
            try:
                # Release only this request's keys even if focus changed.
                _key(lifetime, session, symbol, False)
            except GLib.Error as error:
                # The established owner cancellation path closes its session
                # and releases virtual devices. Never retain unknown modifiers.
                raise OperationStopped("Terminal key release unconfirmed") from error
    return result


def main() -> int:
    if len(sys.argv) != 2:
        raise ValueError("expected one original Terminal window observation")
    observation = WindowObservation.from_json(sys.argv[1])
    status = probe_gnome(
        "ActiveApp",
        {"GetActiveWindow", "GetActiveWindowToken", "GetActiveWindowAndPointer"},
        run=run_process,
    )
    if not status.ready:
        raise BackendUnavailable(status)
    acquired = shared_session(1)
    if acquired is None:
        print("CONTROL_SETUP_REQUIRED", flush=True)
        return 3
    lifetime, session = acquired
    try:
        result = _tab(observation, lifetime, session)
        print(result, flush=True)
        return 0 if result == "TAB_ITEM:ACTION_DISPATCHED" else 2
    finally:
        lifetime.close()


if __name__ == "__main__":
    raise SystemExit(main())
