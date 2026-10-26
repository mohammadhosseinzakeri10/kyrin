"""Platform-independent contract for a fresh foreground-app observation."""

from typing import Protocol


class ActiveAppObserver(Protocol):
    """Return a configured app ID, or None when current focus is unknown."""

    def observe_active_app(self) -> str | None: ...
