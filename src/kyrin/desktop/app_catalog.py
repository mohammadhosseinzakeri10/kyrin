"""Platform-neutral descriptions of applications registered on a device."""

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class InstalledApp:
    """A platform ID and a user-facing label; neither proves current focus."""

    platform_id: str
    display_name: str


class AppCatalog(Protocol):
    """Discover registered apps without guessing which one is active."""

    def list_apps(self) -> tuple[InstalledApp, ...]: ...

    def find_app(self, platform_id: str) -> InstalledApp | None: ...
