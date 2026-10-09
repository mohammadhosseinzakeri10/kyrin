"""Platform-neutral requests to control one existing application window."""

from enum import StrEnum
from typing import Protocol


class WindowOperation(StrEnum):
    RESTORE = "restore"
    MINIMIZE = "minimize"
    CLOSE = "close"
    MAXIMIZE = "maximize"
    UNMAXIMIZE = "unmaximize"
    FULLSCREEN = "fullscreen"
    UNFULLSCREEN = "unfullscreen"


class WindowControlStatus(StrEnum):
    CONFIRMED = "confirmed"
    NO_WINDOW = "no_window"
    MULTIPLE_WINDOWS = "multiple_windows"
    UNAVAILABLE = "unavailable"
    UNKNOWN = "unknown"


class AppWindowController(Protocol):
    def control(self, app_id: str, operation: WindowOperation) -> WindowControlStatus:
        """Control exactly one existing window; never launch or terminate a process."""
