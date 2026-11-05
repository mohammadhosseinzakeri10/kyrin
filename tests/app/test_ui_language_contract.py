"""V1 starts in English while preserving an existing interface choice."""

from pathlib import Path

import pytest

from kyrin.app.qt.translations import UiPreferences, UiTranslations


@pytest.mark.parametrize("system_locale", ["en-US", "fa-IR", "fa_IR", "de-DE"])
def test_fresh_install_uses_english_without_writing_preferences(
    tmp_path: Path, system_locale: str
) -> None:
    directory = tmp_path / "ui"
    translations = UiTranslations(directory, system_locale=system_locale)

    assert translations.active_locale == "en"
    assert translations.preferences.locale == "en"
    assert translations.text("dashboard") == "Dashboard"
    assert not directory.exists()


@pytest.mark.parametrize("choice", ["en", "fa", "system"])
def test_existing_language_selection_survives_english_v1_defaults(
    tmp_path: Path, choice: str
) -> None:
    directory = tmp_path / "ui"
    translations = UiTranslations(directory, system_locale="fa_IR")
    preferences = UiPreferences(choice, False, "gpu_medium")
    translations.save(preferences)
    saved = (directory / "ui.json").read_bytes()

    restored = UiTranslations(directory, system_locale="fa_IR")

    assert restored.preferences == preferences
    assert restored.active_locale == ("en" if choice == "en" else "fa")
    assert (directory / "ui.json").read_bytes() == saved
