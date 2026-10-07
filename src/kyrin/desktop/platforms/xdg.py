"""Read freedesktop application entries without a Python GUI dependency."""

import configparser
import os
from collections.abc import Sequence
from pathlib import Path

from kyrin.desktop.app_catalog import InstalledApp


def _default_data_roots() -> tuple[Path, ...]:
    data_home = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local/share")
    data_dirs = os.environ.get("XDG_DATA_DIRS") or "/usr/local/share:/usr/share"
    return (Path(data_home), *(Path(item) for item in data_dirs.split(":")))


def _read_app(path: Path, platform_id: str) -> InstalledApp | None:
    parser = configparser.ConfigParser(interpolation=None, strict=False)
    try:
        with path.open(encoding="utf-8") as entry_file:
            parser.read_file(entry_file)
    except OSError, UnicodeError, configparser.Error:
        return None
    if not parser.has_section("Desktop Entry"):
        return None
    entry = parser["Desktop Entry"]
    if entry.get("Hidden", "false").lower() == "true":
        return None
    if entry.get("Type") != "Application":
        return None
    name = entry.get("Name", "").strip()
    return InstalledApp(platform_id, name) if name else None


class XdgDesktopAppCatalog:
    """Find app IDs in XDG data roots, preferring the user's entries."""

    def __init__(self, data_roots: Sequence[Path] | None = None) -> None:
        self._data_roots = tuple(data_roots) if data_roots is not None else None

    def _entries(self) -> tuple[tuple[Path, InstalledApp], ...]:
        roots = (
            self._data_roots if self._data_roots is not None else _default_data_roots()
        )
        seen: set[str] = set()
        entries: list[tuple[Path, InstalledApp]] = []
        for root in roots:
            if not root.is_absolute():
                continue
            app_dir = root / "applications"
            if not app_dir.is_dir():
                continue
            for path in sorted(app_dir.rglob("*.desktop")):
                platform_id = "-".join(path.relative_to(app_dir).parts)
                if platform_id in seen:
                    continue
                seen.add(platform_id)
                app = _read_app(path, platform_id)
                if app is not None:
                    entries.append((path, app))
        return tuple(sorted(entries, key=lambda item: item[1].platform_id))

    def list_apps(self) -> tuple[InstalledApp, ...]:
        return tuple(app for _, app in self._entries())

    def find_entry(self, entry_path: Path) -> InstalledApp | None:
        """Identify an exact registered entry, respecting XDG precedence."""
        if not entry_path.is_absolute():
            return None
        return next(
            (app for path, app in self._entries() if path == entry_path),
            None,
        )

    def find_app(self, platform_id: str) -> InstalledApp | None:
        return next(
            (app for app in self.list_apps() if app.platform_id == platform_id),
            None,
        )
