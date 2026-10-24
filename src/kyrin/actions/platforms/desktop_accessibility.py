"""Limit AT-SPI traversal to one active top-level window in the process."""

from typing import Any

from kyrin.desktop.accessibility_target import AccessibilityTarget

Control = tuple[Any, AccessibilityTarget, bool, bool | None, tuple[int, int] | None]


def active_accessible_window(desktop: Any, pid: int, atspi: Any) -> Any:
    """Ambiguous/missing active windows supply no control evidence.

    ACTIVE is a window state, unlike FOCUSED on its keyboard-focus child:
    https://docs.gtk.org/atspi2/enum.StateType.html
    Callers handle transport errors and bracket traversal with GNOME's token.
    """
    windows = []
    for index in range(desktop.get_child_count()):
        app = desktop.get_child_at_index(index)
        if app.get_process_id() != pid:
            continue
        count = app.get_child_count()
        if count > 200:
            raise ControlUnavailable("incomplete window inventory")
        for child_index in range(count):
            window = app.get_child_at_index(child_index)
            window.clear_cache()
            if window.get_role() in (
                atspi.Role.FRAME,
                atspi.Role.WINDOW,
                atspi.Role.DIALOG,
            ) and window.get_state_set().contains(atspi.StateType.ACTIVE):
                windows.append(window)
    return windows[0] if len(windows) == 1 else None


class ControlUnavailable(ValueError):
    """Unsafe, ambiguous or incomplete accessibility evidence; never click instead."""


def _roles(atspi: Any) -> tuple[set[Any], set[Any]]:
    states = {
        atspi.Role.CHECK_BOX,
        atspi.Role.CHECK_MENU_ITEM,
        atspi.Role.SWITCH,
        atspi.Role.TOGGLE_BUTTON,
    }
    clicks = states | {
        atspi.Role.BUTTON,
        atspi.Role.ICON,
        atspi.Role.LINK,
        atspi.Role.MENU_ITEM,
        atspi.Role.PUSH_BUTTON_MENU,
        atspi.Role.RADIO_BUTTON,
        atspi.Role.RADIO_MENU_ITEM,
    }
    return states, clicks


def valid_node(node: Any, atspi: Any, *, interactive: bool = False) -> bool:
    node.clear_cache()
    state = node.get_state_set()
    required = [atspi.StateType.VISIBLE, atspi.StateType.SHOWING]
    if interactive:
        required += [atspi.StateType.ENABLED, atspi.StateType.SENSITIVE]
    return all(state.contains(item) for item in required) and not any(
        state.contains(item)
        for item in (
            atspi.StateType.DEFUNCT,
            atspi.StateType.STALE,
            atspi.StateType.INVALID,
        )
    )


def control_snapshot(
    desktop: Any, pid: int, atspi: Any, frame: tuple[int, int, int, int]
) -> list[Control]:
    """Keep invalid named candidates too, so they cannot authorize OCR fallback.

    Traversal and parent links must agree. A nested top-level window is never
    part of the active window's control tree. Incomplete scans fail closed.
    """
    window = active_accessible_window(desktop, pid, atspi)
    if window is None:
        # No exported application is a missing capability; an exported but
        # ambiguous/inactive window is unsafe evidence.
        if any(
            desktop.get_child_at_index(i).get_process_id() == pid
            for i in range(desktop.get_child_count())
        ):
            raise ControlUnavailable("no unique active window")
        return []
    if not valid_node(window, atspi):
        raise ControlUnavailable("invalid active window")
    component = window.get_component_iface()
    if component is None:
        raise ControlUnavailable("window has no bounds")
    rect = component.get_extents(atspi.CoordType.SCREEN)
    fx, fy, fw, fh = frame
    if not (
        rect.width > 0
        and rect.height > 0
        and fx <= rect.x
        and fy <= rect.y
        and rect.x + rect.width <= fx + fw
        and rect.y + rect.height <= fy + fh
    ):
        raise ControlUnavailable("active window outside focused frame")
    state_roles, click_roles = _roles(atspi)
    window_roles = {atspi.Role.FRAME, atspi.Role.WINDOW, atspi.Role.DIALOG}
    path: tuple[tuple[int, str, str], ...] = (
        (window.get_index_in_parent(), str(window.get_role()), window.get_name()),
    )
    queue: list[tuple[Any, tuple[tuple[int, str, str], ...], bool]] = [
        (window, path, True)
    ]
    found: list[Control] = []
    inspected = 0
    while queue:
        node, ancestry, ancestors_valid = queue.pop()
        inspected += 1
        if inspected > 3000 or len(ancestry) > 100:
            raise ControlUnavailable("incomplete accessibility tree")
        role, name = node.get_role(), node.get_name()
        valid = ancestors_valid and valid_node(node, atspi, interactive=True)
        if node != window and role in window_roles:
            valid = False
        if node.get_process_id() != pid:
            valid = False
        if role in click_roles and 1 <= len(name.strip()) <= 80:
            state = node.get_state_set()
            checked = (
                state.contains(atspi.StateType.CHECKED)
                if role in state_roles
                and not state.contains(atspi.StateType.INDETERMINATE)
                else None
            )
            point = None
            component = node.get_component_iface()
            if component is not None:
                rect = component.get_extents(atspi.CoordType.SCREEN)
                x, y = rect.x + rect.width // 2, rect.y + rect.height // 2
                if (
                    rect.width > 0
                    and rect.height > 0
                    and (fx <= x < fx + fw and fy <= y < fy + fh)
                ):
                    point = (x, y)
                else:
                    valid = False
            found.append(
                (
                    node,
                    AccessibilityTarget(ancestry),
                    valid and valid_node(node, atspi, interactive=True),
                    checked,
                    point,
                )
            )
        count = node.get_child_count()
        if count > 200:
            raise ControlUnavailable("incomplete accessibility children")
        for index in range(count):
            child = node.get_child_at_index(index)
            if child is None or child.get_parent() != node:
                raise ControlUnavailable("inconsistent ancestry")
            queue.append(
                (
                    child,
                    (*ancestry, (index, str(child.get_role()), child.get_name())),
                    valid,
                )
            )
    return found


def resolve_control(
    desktop: Any,
    pid: int,
    atspi: Any,
    frame: tuple[int, int, int, int],
    label: str,
    target: AccessibilityTarget | None = None,
) -> Control | None:
    def normalize(text: str) -> str:
        return " ".join(text.casefold().split())

    matches = [
        item
        for item in control_snapshot(desktop, pid, atspi, frame)
        if normalize(item[0].get_name()) == normalize(label)
    ]
    if not matches:
        if target is not None:
            raise ControlUnavailable("observed control disappeared")
        return None
    if len(matches) != 1 or not matches[0][2]:
        raise ControlUnavailable("ambiguous or invalid control")
    if target is not None and matches[0][1] != target:
        raise ControlUnavailable("role or ancestry changed")
    return matches[0]


def action_index(node: Any, desired: bool | None) -> tuple[Any, int] | None:
    """Only absence of Action permits a coordinate fallback.

    Names from Action.get_action_name are non-localized. Never assume that
    action zero is the primary action.
    """
    action = node.get_action_iface()
    if action is None:
        return None
    count = action.get_n_actions()
    if count == 0:
        return None
    names = [(action.get_action_name(i).casefold(), i) for i in range(count)]
    accepted = (
        {"toggle", "click", "press", "activate"}
        if desired is not None
        else {"click", "press", "activate", "open", "jump"}
    )
    matching = [index for name, index in names if name in accepted]
    if len(matching) != 1:
        raise ControlUnavailable("no unique supported action")
    return action, matching[0]
