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


class AppNameResolver(Protocol):
    def resolve(self, spoken_name: str) -> SpokenAppMatch: ...

    def suggest(self, spoken_name: str) -> SpokenAppMatch:
        """Find possible names for a confirmation question, never an action."""
        ...
