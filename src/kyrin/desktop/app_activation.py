"""An optional desktop adapter for raising an existing application window."""

from enum import StrEnum
from typing import Protocol


class ActivationAttempt(StrEnum):
    REQUESTED = "requested"
    NO_WINDOW = "no_window"
    MULTIPLE_WINDOWS = "multiple_windows"
    UNKNOWN = "unknown"


class ExistingAppActivator(Protocol):
    """Use a registered app ID; never infer a desktop target from speech."""

    def activate_existing_app(self, app_id: str) -> ActivationAttempt: ...
