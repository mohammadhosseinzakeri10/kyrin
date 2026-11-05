"""Replay the owner's unnamed GTK menu Actions against actual helper guards."""

from types import SimpleNamespace

import pytest

from kyrin.actions.platforms.ptyxis_menu import configured_tab_binding, shortcut
from kyrin.desktop.window_observation import WindowObservation
from kyrin.operations import OperationStopped
from tests.actions.test_desktop_semantic_control import Node
from tests.actions.test_desktop_semantic_control import semantic as semantic
from tests.actions.test_gtk4_controls import gtk4, wrapped_menu


@pytest.fixture
def tab_scene(
    semantic: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> SimpleNamespace:
    gtk4(semantic, monkeypatch)
    semantic.atspi.Role.MENU = "MENU"
    semantic.atspi.StateType.EXPANDED = "EXPANDED"
    toggle = wrapped_menu(semantic)
    semantic.window.bounds = (0, 0, 800, 600)
    semantic.window.relative_bounds = (0, 0, 800, 600)
    popup = Node(role="MENU", name="Main Menu", states=set(toggle.states))
    tab = popup.add(
        Node(
            role="MENU_ITEM",
            name="",
            actions=["click"],
            states=set(toggle.states),
            relative_bounds=(100, 100, 90, 20),
        )
    )
    attrs = {"keyshortcuts": "Shift+Control+T Alt+t", "toolkit": "GTK"}
    monkeypatch.setattr(tab, "get_attributes", lambda: attrs, raising=False)
    mapping = {"new-tab": "<ctrl><shift>t", "new-window": "<ctrl><shift>n"}
    settings = SimpleNamespace(
        props=SimpleNamespace(
            settings_schema=SimpleNamespace(list_keys=lambda: tuple(mapping))
        ),
        get_string=lambda key: mapping[key],
    )
    monkeypatch.setattr(
        semantic.helper.Gio,
        "Settings",
        SimpleNamespace(new=lambda name: settings),
        raising=False,
    )
    identity = ("org.gnome.Ptyxis.desktop", 42)
    frame = (*identity, 10, 20, 800, 600, 0, 0)
    monkeypatch.setattr(semantic.helper, "_focused_identity", lambda: identity)
    monkeypatch.setattr(semantic.helper, "_window_and_pointer", lambda: frame)
    observation = WindowObservation(*identity, "window-7", "original", 100, 110)

    def open_menu(index: int | None = None) -> bool:
        if index is not None:
            toggle.calls.append(index)
        if popup not in semantic.node.children:
            semantic.node.add(popup)
        semantic.node.states.add("EXPANDED")
        return True

    monkeypatch.setattr(toggle, "do_action", open_menu)
    return SimpleNamespace(
        scene=semantic,
        toggle=toggle,
        popup=popup,
        tab=tab,
        attrs=attrs,
        mapping=mapping,
        settings=settings,
        observation=observation,
        open_menu=open_menu,
        run=lambda: semantic.helper._semantic_terminal_tab(observation, semantic.owner),
    )


@pytest.mark.parametrize("already_open", [False, True])
def test_unnamed_tab_action_uses_semantic_binding_in_same_window(
    tab_scene: SimpleNamespace,
    already_open: bool,
) -> None:
    t = tab_scene
    if already_open:
        t.open_menu()
    else:
        assert t.run() == "TAB_MENU:TERMINAL_MENU_AUTOMATION_BLOCKED"
        assert t.toggle.calls == [] and t.tab.calls == []
        return
    assert t.run() == "TAB_ITEM:ACTION_DISPATCHED"
    assert t.tab.name == "" and t.tab.calls == [0]
    assert t.toggle.calls == []


@pytest.mark.parametrize(
    "case",
    [
        "disabled",
        "hidden",
        "wrong_binding",
        "duplicate",
        "outside_menu",
        "action",
        "config_conflict",
        "config_disabled",
        "foreign_pid",
        "wrong_menu",
    ],
)
def test_binding_never_rescues_ambiguous_invalid_or_unrelated_action(
    tab_scene: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
    case: str,
) -> None:
    t = tab_scene
    t.open_menu()
    if case == "disabled":
        t.tab.states.remove("SENSITIVE")
    elif case == "hidden":
        t.tab.states.remove("SHOWING")
    elif case == "wrong_binding":
        t.attrs["keyshortcuts"] = "Shift+Control+N"
    elif case == "duplicate":
        other = t.popup.add(
            Node(
                role="MENU_ITEM",
                name="",
                states=set(t.tab.states),
                relative_bounds=(100, 130, 90, 20),
            )
        )
        monkeypatch.setattr(
            other, "get_attributes", lambda: dict(t.attrs), raising=False
        )
    elif case == "outside_menu":
        t.popup.children.remove(t.tab)
        t.scene.panel.add(t.tab)
    elif case == "action":
        t.tab.actions = ["click", "press"]
    elif case == "config_conflict":
        t.mapping["new-window"] = "<control><shift>T"
    elif case == "config_disabled":
        t.mapping["new-tab"] = ""
    elif case == "foreign_pid":
        t.tab.pid = 99
    else:
        t.popup.name = "Other menu"
    result = t.run()
    assert result.startswith(
        ("TAB_ITEM:OBSERVATION_FAILED:", "TAB_MENU:OBSERVATION_FAILED:")
    )
    assert not t.tab.calls


@pytest.mark.parametrize("case", ["focus", "disable", "config", "ancestry", "cancel"])
def test_fresh_commit_checks_and_cancellation_before_tab_action(
    tab_scene: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
    case: str,
) -> None:
    t = tab_scene
    t.open_menu()
    events = []

    def change(*, input_event: bool = False) -> None:
        if input_event:
            events.append(True)
            if len(events) == 1:
                if case == "focus":
                    t.scene.token[0] = "another-window"
                elif case == "disable":
                    t.tab.states.remove("SENSITIVE")
                elif case == "config":
                    t.mapping["new-tab"] = "<ctrl>y"
                elif case == "ancestry":
                    t.popup.children.remove(t.tab)
                    panel = t.popup.add(Node(role="PANEL", name="another"))
                    panel.add(t.tab)
                else:
                    raise OperationStopped("owner cancelled")

    monkeypatch.setattr(t.scene.owner, "check", change)
    if case == "cancel":
        with pytest.raises(OperationStopped):
            t.run()
    else:
        result = t.run()
        assert "ACTION_DISPATCHED" not in result
    assert not t.tab.calls and t.toggle.calls == []


@pytest.mark.parametrize(
    "value", ["<ctrl><shift>t", "Shift+Control+T", "Control+Shift+t"]
)
def test_equivalent_schema_and_live_attribute_forms(value: str) -> None:
    assert shortcut(value) == (frozenset({"control", "shift"}), "t")


@pytest.mark.parametrize(
    "value", ["", "Alt+t", "Ctrl+Shift+t+N", "<ctrl>t trailing", "<untrusted>t"]
)
def test_unknown_or_different_binding_is_not_new_tab(value: str) -> None:
    assert shortcut(value) != shortcut("<ctrl><shift>t")


def test_disabled_and_conflicting_schema_bindings_are_unavailable() -> None:
    from kyrin.actions.platforms.desktop_accessibility import ControlUnavailable

    for mapping in ({"new-tab": ""}, {"new-tab": "<ctrl>t", "new-window": "Control+t"}):
        with pytest.raises(ControlUnavailable):
            configured_tab_binding(tuple(mapping), mapping.__getitem__)


def test_literal_name_baseline_misses_same_unnamed_action_that_semantic_route_executes(
    tab_scene: SimpleNamespace,
) -> None:
    t = tab_scene
    t.open_menu()
    before = t.scene.helper._semantic_control(
        t.observation.identity, "New Tab", None, t.observation, t.scene.owner
    )
    assert before == "NO_ACCESSIBLE_ACTION" and not t.tab.calls
    assert t.run() == "TAB_ITEM:ACTION_DISPATCHED"
    assert t.tab.calls == [0] and not t.toggle.calls


def test_complete_adapter_client_and_helper_keep_one_input_owner(
    tab_scene: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import subprocess
    from time import monotonic

    from kyrin.actions.desktop_input import DesktopInputBroker, DesktopInputExecutor
    from kyrin.actions.models import ActionKey, ActionOutcome, ActionRequest
    from kyrin.actions.platforms import desktop_control
    from kyrin.actions.platforms.ptyxis_tabs import PtyxisTabExecutor
    from kyrin.app.permissions import PermissionPolicy
    from kyrin.app.settings import AllowedApp, AppSettings
    from kyrin.commands.models import CommandIntent, CommandKind
    from tests.actions.test_ptyxis_tabs import Inert

    t = tab_scene
    t.open_menu()
    app = "org.gnome.Ptyxis.desktop"
    now = monotonic()
    t.scene.now[0] = now
    observation = WindowObservation(app, 42, "window-7", "bound", now, now + 10)
    permissions = PermissionPolicy(
        AppSettings(
            action_execution_enabled=True,
            allowed_apps=(AllowedApp("terminal", app),),
            allow_desktop_control=True,
        )
    )
    broker = DesktopInputBroker()
    controls = desktop_control.DesktopControlExecutor(
        Inert(),
        permissions=permissions,
        identity_reader=lambda: (app, 42),
        token_reader=lambda: t.scene.token[0],
    )
    calls = []

    def transport(
        args: list[str], **kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        assert args[2] == "ptyxis-tab" and kwargs["helper"] is True
        assert broker._owner is not None
        bound = WindowObservation.from_json(args[3])
        assert bound == observation
        result = t.scene.helper._semantic_terminal_tab(bound, t.scene.owner)
        calls.append(result)
        return subprocess.CompletedProcess(
            args, 0 if result.endswith("ACTION_DISPATCHED") else 2, result, ""
        )

    monkeypatch.setattr(desktop_control, "run_process", transport)
    adapter = PtyxisTabExecutor(
        Inert(),
        controls,
        app_id="terminal",
        desktop_id=app,
        permissions=permissions,
        identity_reader=lambda: (app, 42),
        token_reader=lambda: t.scene.token[0],
    )
    executor = DesktopInputExecutor(adapter, broker)
    result = executor.execute(
        ActionRequest(
            ActionKey(0, 1),
            CommandIntent(
                CommandKind.NEW_APP_TAB, "terminal", tab_observation=observation
            ),
        )
    )
    assert result.outcome is ActionOutcome.DISPATCHED_UNVERIFIED
    assert calls == ["TAB_ITEM:ACTION_DISPATCHED"] and t.tab.calls == [0]
    assert broker._owner is None
    broker.close()


def test_menu_scope_uses_name_from_refreshed_node_not_pre_refresh_cache(
    tab_scene: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from kyrin.actions.platforms.ptyxis_menu import locate_tab

    t = tab_scene
    t.open_menu()
    refreshed = [False]
    window_clear = t.scene.window.clear_cache

    def reset_cache() -> None:
        window_clear()
        refreshed[0] = False

    def refresh_popup() -> None:
        refreshed[0] = True

    monkeypatch.setattr(t.scene.window, "clear_cache", reset_cache)
    monkeypatch.setattr(t.popup, "clear_cache", refresh_popup)
    monkeypatch.setattr(
        t.popup, "get_name", lambda: "Main Menu" if refreshed[0] else ""
    )
    binding = shortcut("<ctrl><shift>t")
    assert binding is not None
    item = locate_tab(
        t.scene.desktop,
        42,
        t.scene.atspi,
        (10, 20, 800, 600),
        binding,
    )
    assert item is not None and item[0] is t.tab


def test_closed_terminal_menu_cannot_repeat_incident_activation(
    tab_scene: SimpleNamespace,
) -> None:
    t = tab_scene
    assert t.run() == "TAB_MENU:TERMINAL_MENU_AUTOMATION_BLOCKED"
    assert t.toggle.calls == [] and t.tab.calls == []


def test_literal_terminal_menu_click_cannot_bypass_incident_containment(
    tab_scene: SimpleNamespace,
) -> None:
    t = tab_scene
    assert t.scene.helper._semantic_control(
        t.observation.identity, "Main Menu", None, t.observation, t.scene.owner
    ) == "TERMINAL_MENU_AUTOMATION_BLOCKED"
    assert t.toggle.calls == [] and t.tab.calls == []
