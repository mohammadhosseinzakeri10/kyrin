"""Platform-neutral descriptions of applications registered on a device."""

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class InstalledApp:
    """Registered app metadata; neither its name nor categories prove focus."""

    platform_id: str
    display_name: str
    categories: tuple[str, ...] = ()


class AppCatalog(Protocol):
    """Discover registered apps without guessing which one is active."""

    def list_apps(self) -> tuple[InstalledApp, ...]: ...

    def find_app(self, platform_id: str) -> InstalledApp | None: ...
