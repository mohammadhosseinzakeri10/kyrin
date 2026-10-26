"""Backend-independent results for resolving spoken application names."""

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class SpokenAppCandidate:
    app_id: str
    display_name: str


@dataclass(frozen=True, slots=True)
class SpokenAppMatch:
    candidates: tuple[SpokenAppCandidate, ...] = ()
    exact: bool = False


@dataclass(frozen=True, slots=True)
class ModelAppOption:
    """An installed, permitted application shown to the command model."""

    app_id: str
    platform_id: str
    display_name: str
    alternate_names: tuple[str, ...] = ()


class AppNameResolver(Protocol):
    def resolve(self, spoken_name: str) -> SpokenAppMatch: ...

    def model_options(self) -> tuple[ModelAppOption, ...]:
        """Return installed application names available to command inference."""
        ...

    def suggest(self, spoken_name: str) -> SpokenAppMatch:
        """Find possible names for a confirmation question, never an action."""
        ...
