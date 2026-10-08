"""Stable, explicit desktop-app choices for the application settings UI."""

import hashlib
import re
from dataclasses import dataclass
from typing import Protocol

from kyrin.app.settings import AllowedApp
from kyrin.desktop.app_catalog import InstalledApp


class AppPickerCatalog(Protocol):
    def list_apps(self) -> tuple[InstalledApp, ...]: ...

    def list_menu_apps(self) -> tuple[InstalledApp, ...]: ...


@dataclass(frozen=True, slots=True)
class AppChoice:
    binding: AllowedApp
    display_name: str
    installed: bool


def app_choices(
    catalog: AppPickerCatalog, existing: tuple[AllowedApp, ...]
) -> tuple[AppChoice, ...]:
    """Preserve saved IDs and disambiguate newly discovered duplicate names."""
    by_desktop_id = {item.desktop_id: item for item in existing}
    used_ids = {item.app_id for item in existing}
    discovered = sorted(
        catalog.list_menu_apps(),
        key=lambda app: (app.display_name.casefold(), app.platform_id),
    )
    choices: list[AppChoice] = []
    discovered_ids: set[str] = set()
    for app in discovered:
        discovered_ids.add(app.platform_id)
        binding = by_desktop_id.get(app.platform_id)
        if binding is None:
            base = re.sub(r"[^a-z0-9]+", "-", app.display_name.casefold()).strip("-")
            base = base or "app"
            if not base[0].isalpha():
                base = f"app-{base}"
            candidate = base
            if candidate in used_ids:
                digest = hashlib.sha256(app.platform_id.encode("utf-8")).hexdigest()[:8]
                candidate = f"{base}-{digest}"
            while candidate in used_ids:
                candidate += "-app"
            binding = AllowedApp(candidate, app.platform_id)
            used_ids.add(candidate)
        choices.append(AppChoice(binding, app.display_name, True))
    all_installed = {app.platform_id: app for app in catalog.list_apps()}
    for binding in existing:
        if binding.desktop_id not in discovered_ids:
            installed = all_installed.get(binding.desktop_id)
            name = (
                installed.display_name if installed is not None else binding.desktop_id
            )
            choices.append(
                AppChoice(
                    binding,
                    name,
                    installed is not None,
                )
            )
    return tuple(choices)
