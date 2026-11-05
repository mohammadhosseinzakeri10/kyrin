"""One bounded, immutable group binding for app-scoped normal window close."""

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from kyrin.desktop.window_control import WindowControlStatus
from kyrin.desktop.window_observation import WindowObservation


@dataclass(frozen=True, slots=True)
class WindowGroupObservation:
    windows: tuple[WindowObservation, ...]

    def __post_init__(self) -> None:
        if not 1 <= len(self.windows) <= 32:
            raise ValueError("group must contain one to 32 windows")
        first = self.windows[0]
        if len({w.window_token for w in self.windows}) != len(self.windows) or any(
            (w.app_id, w.generation, w.observed_at, w.deadline)
            != (first.app_id, first.generation, first.observed_at, first.deadline)
            for w in self.windows
        ):
            raise ValueError("group must bind unique windows of one app/generation")

    @property
    def app_id(self) -> str:
        return self.windows[0].app_id

    @property
    def generation(self) -> str:
        return self.windows[0].generation

    @property
    def deadline(self) -> float:
        return self.windows[0].deadline

    def current(self, now: float) -> bool:
        return all(w.current(w.window_token, now) for w in self.windows)


@runtime_checkable
class AppWindowGroupController(Protocol):
    def prepare_close_all(self, app_id: str) -> WindowGroupObservation | None: ...

    def confirm_close_all(
        self, group: WindowGroupObservation, language: str | None
    ) -> bool: ...

    def close_all_confirmed(
        self, group: WindowGroupObservation
    ) -> WindowControlStatus: ...


@runtime_checkable
class AuthorizedWindowGroupCloser(Protocol):
    """Use saved consent without weakening the original one-use group binding."""

    def close_all_authorized(
        self, group: WindowGroupObservation
    ) -> WindowControlStatus: ...
