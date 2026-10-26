"""Read-only, fresh descriptions of the active application's visible controls."""

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class VisibleElement:
    """An accessibility label, not an action target or a stable selector."""

    role: str
    name: str


@dataclass(frozen=True, slots=True)
class ScreenObservation:
    """One bounded observation; None means it could not be established safely."""

    platform_app_id: str
    accessible_app_name: str
    elements: tuple[VisibleElement, ...]
    truncated: bool = False


class ScreenObserver(Protocol):
    """Observe on demand; never authorize actions from an old observation."""

    def observe(self) -> ScreenObservation | None: ...
