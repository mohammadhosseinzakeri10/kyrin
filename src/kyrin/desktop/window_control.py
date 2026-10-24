"""Platform-neutral requests to control one existing application window."""

from enum import StrEnum
from typing import Protocol

from kyrin.desktop.window_observation import WindowObservation


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

    def prepare_close(
        self, app_id: str, window_index: int | None = None
    ) -> WindowObservation | None:
        """Observe one close target; index refers to the Shell's current picker.

        The platform retains a single-use binding to this selection, focus and
        a maximum ten-second deadline. Preparing never sends a close request.
        """

    def close_confirmed(self, window: WindowObservation) -> WindowControlStatus:
        """Consume a prepared binding, revalidate atomically, request normal close.

        Never substitute another window, renew expiry or answer a native dialog.
        Direct control(CLOSE) must fail closed, without a prepared decision.
        """
