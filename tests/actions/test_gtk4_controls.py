"""Observed GTK4 state mapping and nested menu-button identity, without input."""

from types import SimpleNamespace

import pytest

from kyrin.actions.platforms import desktop_accessibility as accessibility
from tests.actions.test_desktop_semantic_control import (
    Node,
)
from tests.actions.test_desktop_semantic_control import (
    inventory as inventory,
)
from tests.actions.test_desktop_semantic_control import (
    semantic as semantic,
)


def gtk4(scene: SimpleNamespace, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        scene.window, "get_application", lambda: scene.app, raising=False
    )
    monkeypatch.setattr(scene.app, "get_toolkit_name", lambda: "GTK", raising=False)
    monkeypatch.setattr(
        scene.app, "get_toolkit_version", lambda: "4.22.4", raising=False
    )
    monkeypatch.setattr(
        scene.window, "get_attributes", lambda: {"toolkit": "GTK"}, raising=False
    )
    for node in (scene.window, scene.panel, scene.node):
        node.states.discard("ENABLED")


def wrapped_menu(scene: SimpleNamespace) -> Node:
    wrapper = scene.node
    assert isinstance(wrapper, Node)
    wrapper.name = "Main Menu"
    wrapper.actions = []
    wrapper.relative_bounds = (40, 60, 90, 20)
    child = wrapper.add(
        Node(
            role="TOGGLE_BUTTON",
            name="Main Menu",
            actions=["click"],
            bounds=wrapper.bounds,
            relative_bounds=wrapper.relative_bounds,
            states=set(wrapper.states),
        )
    )
    return child


def test_gtk4_sensitive_action_works_without_unreported_enabled(
    semantic: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gtk4(semantic, monkeypatch)
    assert semantic.invoke() == "ACTION_DISPATCHED"
    assert semantic.node.calls == [1]


def test_one_nested_menu_widget_is_not_two_targets(
    semantic: SimpleNamespace,
    inventory: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gtk4(semantic, monkeypatch)
    child = wrapped_menu(semantic)
    reply = inventory.observe_controls("example.desktop", 42, "window-7")
    assert reply.rejection_for("Main Menu") is None
    assert len(reply.controls) == 1
    assert reply.controls[0]["role"] == "TOGGLE_BUTTON"
    assert semantic.invoke(label="Main Menu") == "ACTION_DISPATCHED"
    assert child.calls == [0] and not semantic.node.calls


@pytest.mark.parametrize(
    "case", ["sibling", "geometry", "wrapper_action", "role", "child_action"]
)
def test_independent_or_uncertain_same_named_controls_stay_ambiguous(
    semantic: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
    case: str,
) -> None:
    gtk4(semantic, monkeypatch)
    child = wrapped_menu(semantic)
    if case == "sibling":
        semantic.panel.add(Node(name="Main Menu"))
    elif case == "geometry":
        child.relative_bounds = (60, 60, 90, 20)
    elif case == "wrapper_action":
        semantic.node.actions = ["click"]
    elif case == "role":
        child.role = "BUTTON"
    else:
        child.actions = ["click", "press"]
    with pytest.raises(accessibility.ControlUnavailable):
        semantic.invoke(label="Main Menu")
    assert not child.calls and not semantic.node.calls


@pytest.mark.parametrize(
    "case",
    [
        "insensitive",
        "ancestor",
        "hidden",
        "stale",
        "pid",
        "unknown_toolkit",
        "unknown_version",
        "wrong_attribute",
        "old_gtk",
        "foreign_provider",
        "no_action",
    ],
)
def test_gtk4_compatibility_does_not_erase_validity_or_provider_checks(
    semantic: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
    case: str,
) -> None:
    gtk4(semantic, monkeypatch)
    if case == "insensitive":
        semantic.node.states.remove("SENSITIVE")
    elif case == "ancestor":
        semantic.panel.states.remove("SENSITIVE")
    elif case == "hidden":
        semantic.node.states.remove("SHOWING")
    elif case == "stale":
        semantic.node.states.add("STALE")
    elif case == "pid":
        semantic.node.pid = 99
    elif case == "unknown_toolkit":
        monkeypatch.setattr(semantic.app, "get_toolkit_name", lambda: None)
    elif case == "unknown_version":
        monkeypatch.setattr(semantic.app, "get_toolkit_version", lambda: None)
    elif case == "wrong_attribute":
        monkeypatch.setattr(
            semantic.window, "get_attributes", lambda: {"toolkit": "other"}
        )
    elif case == "old_gtk":
        monkeypatch.setattr(semantic.app, "get_toolkit_version", lambda: "3.24.0")
    elif case == "foreign_provider":
        semantic.app.pid = 99
        assert semantic.invoke() == "NO_ACCESSIBLE_ACTION"
        assert not semantic.node.calls
        return
    else:
        semantic.node.actions = None
    with pytest.raises(accessibility.ControlUnavailable):
        semantic.invoke()
    assert not semantic.node.calls


def test_disabled_during_helper_authorization_never_invokes_action(
    semantic: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gtk4(semantic, monkeypatch)

    def disable(*, input_event: bool = False) -> None:
        if input_event:
            semantic.node.states.remove("SENSITIVE")

    monkeypatch.setattr(semantic.owner, "check", disable)
    with pytest.raises(accessibility.ControlUnavailable):
        semantic.invoke()
    assert not semantic.node.calls


@pytest.mark.parametrize("actions", [["show menu"], ["click", "press"]])
def test_unsupported_other_control_does_not_invalidate_valid_target(
    semantic: SimpleNamespace,
    inventory: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
    actions: list[str],
) -> None:
    gtk4(semantic, monkeypatch)
    other = semantic.panel.add(
        Node(name="Other", actions=actions, states=set(semantic.node.states))
    )
    reply = inventory.observe_controls("example.desktop", 42, "window-7")
    assert reply.status == "ok"
    assert reply.rejection_for("Other") == "target_invalid"
    assert semantic.invoke() == "ACTION_DISPATCHED"
    assert not other.calls
