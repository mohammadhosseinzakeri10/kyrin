"""Image sources are separate from text recognition and desktop actions."""

from dataclasses import dataclass
from typing import Protocol


class ScreenCapture(Protocol):
    def capture_window(self) -> bytes | None:
        """Ask the user to select a window and return one image in memory."""
        ...


@dataclass(frozen=True, slots=True)
class IdentifiedWindowImage:
    """A capture tied to one focused app at capture time, not action authority."""

    platform_app_id: str
    process_id: int
    image: bytes
    capture_rect: tuple[int, int, int, int] | None = None
    frame_rect: tuple[int, int, int, int] | None = None

    def __post_init__(self) -> None:
        if (
            not isinstance(self.platform_app_id, str)
            or not self.platform_app_id.strip()
            or type(self.process_id) is not int
        ):
            raise ValueError("captured window identity is missing")
        if self.process_id <= 0 or not self.image.startswith(b"\x89PNG\r\n\x1a\n"):
            raise ValueError("captured window image is invalid")
        for rect in (self.capture_rect, self.frame_rect):
            if rect is not None and (
                len(rect) != 4
                or any(type(value) is not int for value in rect)
                or rect[2] <= 0
                or rect[3] <= 0
            ):
                raise ValueError("captured window geometry is invalid")


class ActiveWindowCapture(Protocol):
    def capture_active_window(self) -> IdentifiedWindowImage | None:
        """Read only the currently focused window; fail closed on focus changes."""
        ...
