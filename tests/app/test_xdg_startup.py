"""User-scoped startup entries are reversible and never replace foreign files."""

from pathlib import Path

import pytest

from kyrin.app.platforms.xdg_startup import (
    DESKTOP_FILE_ID,
    DesktopRegistrationError,
    XdgDesktopRegistration,
    user_desktop_paths,
)


def _registration(root: Path) -> XdgDesktopRegistration:
    executable = root / "app install" / "kyrin-desktop"
    executable.parent.mkdir()
    executable.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    executable.chmod(0o700)
    icon = root / "kyrin-logo.png"
    icon.write_bytes(b"placeholder icon")
    return XdgDesktopRegistration(
        executable,
        root / "data/applications/local.kyrin.KYRIN.desktop",
        root / "config/autostart/local.kyrin.KYRIN.desktop",
        icon_path=icon,
    )


def test_enable_creates_menu_and_autostart_then_disable_keeps_menu(
    tmp_path: Path,
) -> None:
    registration = _registration(tmp_path)
    assert not registration.enabled()

    registration.set_enabled(True)

    assert registration.enabled()
    menu = registration.menu_path.read_text(encoding="utf-8")
    assert 'Exec="' in menu
    assert "app install" in menu
    assert f"Icon={registration.icon_path}" in menu
    assert "X-KYRIN-Managed=true" in menu
    assert registration.autostart_path.read_text(encoding="utf-8") == menu

    registration.set_enabled(False)

    assert not registration.enabled()
    assert not registration.autostart_path.exists()
    assert registration.menu_path.exists()


def test_foreign_autostart_file_is_not_overwritten_or_removed(tmp_path: Path) -> None:
    registration = _registration(tmp_path)
    registration.autostart_path.parent.mkdir(parents=True)
    registration.autostart_path.write_text("[Desktop Entry]\nName=Other\n")

    with pytest.raises(DesktopRegistrationError, match="Unmanaged"):
        registration.set_enabled(True)
    with pytest.raises(DesktopRegistrationError, match="Unmanaged"):
        registration.set_enabled(False)

    assert registration.autostart_path.read_text() == "[Desktop Entry]\nName=Other\n"


def test_xdg_paths_respect_absolute_overrides(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    menu, autostart = user_desktop_paths()
    assert menu.stem == DESKTOP_FILE_ID
    assert menu == tmp_path / "data/applications/local.kyrin.KYRIN.desktop"
    assert autostart == tmp_path / "config/autostart/local.kyrin.KYRIN.desktop"
