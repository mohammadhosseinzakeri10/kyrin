"""XDG app discovery uses exact IDs and respects search precedence."""

from pathlib import Path

from kyrin.desktop.app_catalog import InstalledApp
from kyrin.desktop.platforms.xdg import XdgDesktopAppCatalog


def _entry(root: Path, relative: str, *, name: str, extra: str = "") -> None:
    path = root / "applications" / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"[Desktop Entry]\nType=Application\nName={name}\n{extra}",
        encoding="utf-8",
    )


def test_discovers_nested_ids_and_distinguishes_equal_names(tmp_path: Path) -> None:
    root = tmp_path / "data"
    _entry(root, "foo/bar.desktop", name="Browser")
    _entry(root, "another.desktop", name="Browser")
    catalog = XdgDesktopAppCatalog((root,))

    assert catalog.list_apps() == (
        InstalledApp("another.desktop", "Browser"),
        InstalledApp("foo-bar.desktop", "Browser"),
    )
    assert catalog.find_app("foo-bar.desktop") == InstalledApp(
        "foo-bar.desktop", "Browser"
    )
    assert catalog.find_app("Browser") is None


def test_user_entry_precedes_system_entry(tmp_path: Path) -> None:
    user = tmp_path / "user"
    system = tmp_path / "system"
    _entry(user, "chat.desktop", name="User Chat")
    _entry(system, "chat.desktop", name="System Chat")

    assert XdgDesktopAppCatalog((user, system)).list_apps() == (
        InstalledApp("chat.desktop", "User Chat"),
    )


def test_hidden_user_entry_masks_system_entry(tmp_path: Path) -> None:
    user = tmp_path / "user"
    system = tmp_path / "system"
    _entry(user, "chat.desktop", name="Hidden Chat", extra="Hidden=true\n")
    _entry(system, "chat.desktop", name="System Chat")

    assert XdgDesktopAppCatalog((user, system)).find_app("chat.desktop") is None


def test_no_display_app_is_registered_but_non_app_is_skipped(tmp_path: Path) -> None:
    root = tmp_path / "data"
    _entry(root, "background.desktop", name="Background", extra="NoDisplay=true\n")
    path = root / "applications" / "link.desktop"
    path.write_text("[Desktop Entry]\nType=Link\nName=Site\n", encoding="utf-8")

    assert XdgDesktopAppCatalog((root,)).list_apps() == (
        InstalledApp("background.desktop", "Background"),
    )
