"""Ptyxis menu semantics when GTK exports click actions without item names.

The live item's keyshortcuts must agree uniquely with the owner's unchanged
Ptyxis Shortcuts schema. These strings identify an Action; no keys are sent.
"""

import re
from collections.abc import Callable, Sequence
from typing import Any

from kyrin.actions.platforms.desktop_accessibility import (
    Control,
    ControlUnavailable,
    control_snapshot,
)
from kyrin.desktop.accessibility_target import AccessibilityTarget

Binding = tuple[frozenset[str], str]
_MODIFIERS = {
    "ctrl": "control",
    "control": "control",
    "shift": "shift",
    "alt": "alt",
    "super": "super",
    "meta": "meta",
}


def shortcut(value: str) -> Binding | None:
    text = value.strip().casefold()
    if not text or len(text) > 100:
        return None
    if text.startswith("<"):
        modifiers = re.findall(r"<([^<>]+)>", text)
        key = re.sub(r"<[^<>]+>", "", text)
        if text != "".join(f"<{part}>" for part in modifiers) + key:
            return None
    else:
        *modifiers, key = text.split("+")
    if any(part not in _MODIFIERS for part in modifiers) or not re.fullmatch(
        r"[a-z0-9]|f(?:[1-9]|[12][0-9]|3[0-5])", key
    ):
        return None
    normalized = [_MODIFIERS[part] for part in modifiers]
    if len(set(normalized)) != len(normalized):
        return None
    return frozenset(normalized), key


def configured_tab_binding(keys: Sequence[str], read: Callable[[str], str]) -> Binding:
    if not 1 <= len(keys) <= 200 or "new-tab" not in keys:
        raise ControlUnavailable("no unique supported action")
    binding = shortcut(read("new-tab"))
    if binding is None or any(
        key != "new-tab" and shortcut(read(key)) == binding for key in keys
    ):
        raise ControlUnavailable("no unique supported action")
    return binding


def locate_tab(
    desktop: Any,
    pid: int,
    atspi: Any,
    frame: tuple[int, int, int, int],
    binding: Binding,
    target: AccessibilityTarget | None = None,
) -> Control | None:
    matches: list[Control] = []
    for item in control_snapshot(desktop, pid, atspi, frame, unnamed_menu_items=True):
        node, structure, valid, _checked, _point = item
        if node.get_role() != atspi.Role.MENU_ITEM:
            continue
        if not any(
            role == str(atspi.Role.MENU) and name == "Main Menu"
            for _, role, name in structure.ancestry
        ):
            continue
        advertised = node.get_attributes().get("keyshortcuts", "")
        if (
            not isinstance(advertised, str)
            or len(advertised) > 256
            or binding not in {shortcut(part) for part in advertised.split()}
        ):
            continue
        matches.append(item)
    if not matches:
        if target is not None:
            raise ControlUnavailable("observed control disappeared")
        return None
    if len(matches) != 1:
        raise ControlUnavailable("ambiguous control")
    if not matches[0][2]:
        raise ControlUnavailable("invalid control")
    if target is not None and matches[0][1] != target:
        raise ControlUnavailable("role or ancestry changed")
    return matches[0]
