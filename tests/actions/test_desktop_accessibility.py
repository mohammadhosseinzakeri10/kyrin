"""Two identical windows in one process do not share a control subtree."""

from dataclasses import dataclass, field
from types import SimpleNamespace

from kyrin.actions.platforms.desktop_accessibility import active_accessible_window


@dataclass
class Node:
    role: str = "FRAME"
    active: bool = False
    pid: int = 42
    children: list[Node] = field(default_factory=list)

    def get_child_count(self) -> int:
        return len(self.children)

    def get_child_at_index(self, index: int) -> Node:
        return self.children[index]

    def get_process_id(self) -> int:
        return self.pid

    def get_role(self) -> str:
        return self.role

    def clear_cache(self) -> None:
        pass

    def get_state_set(self) -> Node:
        return self

    def contains(self, state: str) -> bool:
        assert state == "ACTIVE"
        return self.active


ATSPI = SimpleNamespace(
    Role=SimpleNamespace(FRAME="FRAME", WINDOW="WINDOW", DIALOG="DIALOG"),
    StateType=SimpleNamespace(ACTIVE="ACTIVE"),
)


def test_only_active_window_supplies_control_subtree() -> None:
    first, second = Node(), Node(active=True)
    desktop = Node(children=[Node(children=[first, second])])
    assert active_accessible_window(desktop, 42, ATSPI) is second
    assert active_accessible_window(desktop, 99, ATSPI) is None
    first.active = True
    assert active_accessible_window(desktop, 42, ATSPI) is None
    first.active = second.active = False
    assert active_accessible_window(desktop, 42, ATSPI) is None
