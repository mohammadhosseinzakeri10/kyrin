"""Platform-neutral, read-only observation of a registered app's windows."""

from enum import StrEnum
from typing import Protocol


class WindowPresence(StrEnum):
    OPEN = "open"
    CLOSED = "closed"
    UNKNOWN = "unknown"


class AppWindowPresence(Protocol):
    def observe(self, app_id: str) -> WindowPresence:
        """Read fresh state; never infer it from an earlier command."""

    def count(self, app_id: str) -> int | None:
        """Return a fresh window count, or None when the adapter is unavailable."""
