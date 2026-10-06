"""Labels and unknown catalog entries cannot create a trusted app identity."""

from pathlib import Path

import pytest

from kyrin.desktop.app_identity import AppIdentityResolver
from kyrin.desktop.platforms.xdg import XdgDesktopAppCatalog


def _entry(root: Path, file_name: str, name: str) -> None:
    app_dir = root / "applications"
    app_dir.mkdir(parents=True, exist_ok=True)
    (app_dir / file_name).write_text(
        f"[Desktop Entry]\nType=Application\nName={name}\n", encoding="utf-8"
    )


def test_exact_selected_id_must_exist_in_catalog(tmp_path: Path) -> None:
    _entry(tmp_path, "telegram-local.desktop", "Telegram")
    resolver = AppIdentityResolver(
        {
            "telegram-local.desktop": "telegram",
            "telegram-other.desktop": "telegram",
        },
        XdgDesktopAppCatalog((tmp_path,)),
    )

    assert resolver.resolve("telegram-local.desktop") == "telegram"
    assert resolver.resolve("telegram-other.desktop") is None
    assert resolver.resolve("Telegram") is None
    assert resolver.resolve(None) is None


def test_duplicate_display_names_do_not_create_binding(tmp_path: Path) -> None:
    _entry(tmp_path, "chrome-a.desktop", "Google Chrome")
    _entry(tmp_path, "chrome-b.desktop", "Google Chrome")
    resolver = AppIdentityResolver(
        {"chrome-a.desktop": "browser"}, XdgDesktopAppCatalog((tmp_path,))
    )

    assert resolver.resolve("chrome-a.desktop") == "browser"
    assert resolver.resolve("chrome-b.desktop") is None


def test_empty_binding_is_rejected() -> None:
    with pytest.raises(ValueError, match="identifiers"):
        AppIdentityResolver({"app.desktop": ""})
