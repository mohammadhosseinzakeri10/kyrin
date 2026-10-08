"""UI language packs are independent of speech recognition settings."""

import json
from pathlib import Path

import pytest

from kyrin.app.qt.translations import (
    ENGLISH,
    TranslationError,
    UiPreferences,
    UiTranslations,
)


def test_import_and_select_complete_language_pack(tmp_path: Path) -> None:
    store = UiTranslations(tmp_path / "ui")
    source = tmp_path / "translation.json"
    localized = dict(ENGLISH, dashboard="Tableau de bord")
    source.write_text(
        json.dumps({"locale": "fr", "name": "Français", "strings": localized}),
        encoding="utf-8",
    )

    assert store.import_pack(source) == "fr"
    store.save(UiPreferences("fr"))
    restored = UiTranslations(tmp_path / "ui")

    assert restored.text("dashboard") == "Tableau de bord"
    assert restored.preferences == UiPreferences("fr")
    assert ("fr", "Français") in restored.languages()


def test_incomplete_pack_does_not_replace_installed_pack(tmp_path: Path) -> None:
    store = UiTranslations(tmp_path / "ui")
    source = tmp_path / "translation.json"
    source.write_text(
        json.dumps({"locale": "fr", "name": "Français", "strings": {"dashboard": "X"}}),
        encoding="utf-8",
    )

    with pytest.raises(TranslationError, match="every UI string"):
        store.import_pack(source)

    assert store.languages() == (("en", "English"),)
    assert not (tmp_path / "ui" / "languages" / "fr.json").exists()


def test_corrupt_ui_preferences_keep_app_usable_and_file_untouched(
    tmp_path: Path,
) -> None:
    directory = tmp_path / "ui"
    directory.mkdir()
    damaged = directory / "ui.json"
    damaged.write_text("{broken", encoding="utf-8")

    store = UiTranslations(directory)

    assert store.preferences == UiPreferences()
    assert store.load_error is not None
    assert store.text("dashboard") == "Dashboard"
    assert damaged.read_text(encoding="utf-8") == "{broken"


def test_missing_selected_pack_falls_back_to_english_without_rewriting_choice(
    tmp_path: Path,
) -> None:
    directory = tmp_path / "ui"
    directory.mkdir()
    selection = directory / "ui.json"
    selection.write_text('{"locale": "fr"}', encoding="utf-8")

    store = UiTranslations(directory)

    assert store.load_error is not None
    assert store.preferences.locale == "en"
    assert store.text("dashboard") == "Dashboard"
    assert selection.read_text(encoding="utf-8") == '{"locale": "fr"}'
