"""Live Telegram menu/search locators; missing semantics never imply a position."""

from dataclasses import dataclass
from typing import Any

from kyrin.actions.platforms.desktop_accessibility import (
    ControlUnavailable,
    active_accessible_window,
    valid_node,
)
from kyrin.desktop.accessibility_target import AccessibilityTarget
from kyrin.operations import check_operation

# Exact accessible labels only. Other translations/builds fail closed.
MENU_LABELS = frozenset({"main menu", "منوی اصلی"})
SEARCH_LABELS = frozenset({"search", "جستجو", "جست‌وجو"})


@dataclass(frozen=True)
class TelegramControl:
    node: Any
    target: AccessibilityTarget
    bounds: tuple[int, int, int, int]


def locate_control(
    atspi: Any, pid: int, frame: tuple[int, int, int, int], kind: str
) -> TelegramControl:
    """Resolve a unique live node inside the sole active window, in any layout."""
    window = active_accessible_window(atspi.get_desktop(0), pid, atspi)
    if window is None:
        raise ControlUnavailable("Telegram has no unique accessible window")
    labels = MENU_LABELS if kind == "menu" else SEARCH_LABELS
    roles = (
        {atspi.Role.PUSH_BUTTON_MENU, atspi.Role.BUTTON}
        if kind == "menu"
        else {atspi.Role.ENTRY, atspi.Role.TEXT}
    )
    window_roles = {atspi.Role.FRAME, atspi.Role.WINDOW, atspi.Role.DIALOG}
    queue: list[tuple[Any, tuple[tuple[int, str, str], ...], bool]] = [
        (window, (), True)
    ]
    matches: list[TelegramControl] = []
    inspected = 0
    fx, fy, fw, fh = frame
    while queue:
        check_operation()
        node, ancestry, parents_valid = queue.pop()
        inspected += 1
        if inspected > 3000 or len(ancestry) >= 100:
            raise ControlUnavailable("incomplete Telegram accessibility tree")
        node.clear_cache()
        role, name = node.get_role(), node.get_name()
        path = (*ancestry, (node.get_index_in_parent(), str(role), name))
        valid = (
            parents_valid
            and valid_node(node, atspi, interactive=True)
            and node.get_process_id() == pid
            and (node == window or role not in window_roles)
        )
        if node == window or (
            role in roles and " ".join(name.casefold().split()) in labels
        ):
            component = node.get_component_iface()
            if component is None:
                raise ControlUnavailable("Telegram control has no bounds")
            rect = component.get_extents(atspi.CoordType.SCREEN)
            bounds = (rect.x, rect.y, rect.width, rect.height)
            if not (
                valid
                and rect.width > 0
                and rect.height > 0
                and fx <= rect.x
                and fy <= rect.y
                and rect.x + rect.width <= fx + fw
                and rect.y + rect.height <= fy + fh
            ):
                raise ControlUnavailable("invalid Telegram control")
            if node != window:
                if kind == "search" and (
                    not node.get_state_set().contains(atspi.StateType.EDITABLE)
                    or node.get_editable_text_iface() is None
                    or node.get_text_iface() is None
                ):
                    raise ControlUnavailable("Telegram search is not editable")
                matches.append(TelegramControl(node, AccessibilityTarget(path), bounds))
        count = node.get_child_count()
        if count > 200:
            raise ControlUnavailable("incomplete Telegram children")
        for index in range(count):
            child = node.get_child_at_index(index)
            if child is None or child.get_parent() != node:
                raise ControlUnavailable("inconsistent Telegram ancestry")
            queue.append((child, path, valid))
    if len(matches) != 1:
        raise ControlUnavailable("Telegram control missing or ambiguous")
    return matches[0]
