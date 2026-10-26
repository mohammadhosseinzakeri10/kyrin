"""Short-lived descriptions of controls observed in the focused window."""

from dataclasses import dataclass
from typing import Literal

from kyrin.desktop.accessibility_target import AccessibilityTarget
from kyrin.desktop.window_observation import WindowObservation


@dataclass(frozen=True, slots=True)
class VisibleOption:
    option_id: str
    label: str
    source: Literal["accessibility", "ocr"]
    role: str | None = None
    checked: bool | None = None
    anchor: tuple[int, int] | None = None
    observation: WindowObservation | None = None

    accessibility: AccessibilityTarget | None = None

    def __post_init__(self) -> None:
        if not self.option_id.isdecimal() or not 1 <= len(self.label.strip()) <= 80:
            raise ValueError("visible options need a numeric ID and short label")
        if self.anchor is not None and (
            len(self.anchor) != 2
            or any(type(value) is not int or value < 0 for value in self.anchor)
        ):
            raise ValueError("visible option anchor must be window-relative")
