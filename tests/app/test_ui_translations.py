"""UI language packs are independent of speech recognition settings."""

import json
from pathlib import Path

import pytest

from kyrin.app.qt.locale_fa import PERSIAN
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


def test_dashboard_preferences_round_trip_and_legacy_file(tmp_path: Path) -> None:
    store = UiTranslations(tmp_path / "ui")
    store.save(UiPreferences("fa", False, "gpu_heavy"))
    assert UiTranslations(tmp_path / "ui").preferences == UiPreferences(
        "fa", False, "gpu_heavy"
    )
    store.save(UiPreferences("fa", True, "gpu_medium"))
    assert UiTranslations(tmp_path / "ui").preferences == UiPreferences(
        "fa", True, "gpu_medium"
    )
    (tmp_path / "ui" / "ui.json").write_text(
        json.dumps({"locale": "fa", "dashboard_renderer": "gpu3d"}),
        encoding="utf-8",
    )
    migrated = UiTranslations(tmp_path / "ui")
    assert migrated.preferences == UiPreferences("fa", True, "gpu")
    assert migrated.load_error is None
    (tmp_path / "ui" / "ui.json").write_text(
        json.dumps({"locale": "en"}), encoding="utf-8"
    )
    assert UiTranslations(tmp_path / "ui").preferences == UiPreferences("en")


def test_partial_pack_falls_back_to_english_per_string(tmp_path: Path) -> None:
    store = UiTranslations(tmp_path / "ui")
    source = tmp_path / "translation.json"
    source.write_text(
        json.dumps({"locale": "fr", "name": "Français", "strings": {"dashboard": "X"}}),
        encoding="utf-8",
    )

    store.import_pack(source)
    store.save(UiPreferences("fr"))

    assert store.text("dashboard") == "X"
    assert store.text("actions") == ENGLISH["actions"]
    assert ("fr", "Français") in store.languages()


def test_builtin_persian_is_complete_and_right_to_left(tmp_path: Path) -> None:
    assert set(PERSIAN) == set(ENGLISH)
    store = UiTranslations(tmp_path / "ui")
    store.save(UiPreferences("fa"))
    restored = UiTranslations(tmp_path / "ui")
    assert restored.preferences.locale == "fa"
    assert restored.active_locale == "fa"
    assert restored.text("dashboard") == "داشبورد"
    assert ("fa", "فارسی") in restored.languages()


def test_system_locale_chooses_installed_language_or_english(tmp_path: Path) -> None:
    persian = UiTranslations(tmp_path / "fa", system_locale="fa_IR")
    persian.save(UiPreferences("system"))
    assert UiTranslations(tmp_path / "fa", system_locale="fa_IR").active_locale == "fa"
    assert UiTranslations(tmp_path / "fa", system_locale="de_DE").active_locale == "en"
    assert persian.preferences.locale == "system"


def test_system_locale_can_match_a_script_pack(tmp_path: Path) -> None:
    directory = tmp_path / "ui"
    source = tmp_path / "zh-Hant.json"
    source.write_text(
        json.dumps(
            {
                "locale": "zh-Hant",
                "name": "繁體中文",
                "strings": {"dashboard": "儀表板"},
            }
        ),
        encoding="utf-8",
    )
    store = UiTranslations(directory, system_locale="zh-Hant-TW")
    store.import_pack(source)
    store.save(UiPreferences("system"))
    assert store.active_locale == "zh-Hant"
    assert store.text("dashboard") == "儀表板"


def test_invalid_placeholders_are_rejected_without_writing(tmp_path: Path) -> None:
    store = UiTranslations(tmp_path / "ui")
    source = tmp_path / "bad.json"
    source.write_text(
        json.dumps(
            {
                "locale": "fr",
                "name": "Français",
                "strings": {"command_models_found": "{wrong} modèles trouvés"},
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(TranslationError, match="placeholders"):
        store.import_pack(source)
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


def test_existing_complete_pack_uses_english_for_new_action_labels(
    tmp_path: Path,
) -> None:
    directory = tmp_path / "ui"
    languages = directory / "languages"
    languages.mkdir(parents=True)
    old_strings = {
        key: value
        for key, value in ENGLISH.items()
        if key
        not in {
            "actions",
            "actions_heading",
            "actions_caption",
            "enable_actions",
            "actions_search",
            "action_select_one",
            "app_unavailable",
        }
    }
    old_strings["dashboard"] = "Tableau de bord"
    (languages / "fr.json").write_text(
        json.dumps({"locale": "fr", "name": "Français", "strings": old_strings}),
        encoding="utf-8",
    )
    (directory / "ui.json").write_text('{"locale":"fr"}', encoding="utf-8")

    store = UiTranslations(directory)

    assert store.load_error is None
    assert store.text("dashboard") == "Tableau de bord"
    assert store.text("actions") == "Desktop Actions"


def test_import_older_pack_keeps_new_screen_labels_in_english(
    tmp_path: Path,
) -> None:
    store = UiTranslations(tmp_path / "ui")
    source = tmp_path / "older.json"
    strings = {
        key: value
        for key, value in ENGLISH.items()
        if not key.startswith("screen")
    }
    strings["dashboard"] = "Tableau de bord"
    source.write_text(
        json.dumps({"locale": "fr", "name": "Français", "strings": strings}),
        encoding="utf-8",
    )

    store.import_pack(source)
    store.save(UiPreferences("fr"))

    assert store.text("dashboard") == "Tableau de bord"
    assert store.text("screen_enable") == ENGLISH["screen_enable"]
