"""Saved preferences are validated without reading the owner's home folder."""

import json
import os
from dataclasses import replace
from pathlib import Path

import pytest

from kyrin.app.settings import (
    AllowedApp,
    AppSettings,
    AppSpokenAliases,
    CommandModelSelection,
    OcrSelection,
    SttSelection,
    TtsLanguageRoute,
    TtsSelection,
)
from kyrin.app.settings_store import (
    JsonSettingsStore,
    SettingsError,
    linux_settings_path,
)
from kyrin.stt.device import DevicePreference


def test_missing_settings_start_in_safe_setup_state(tmp_path: Path) -> None:
    store = JsonSettingsStore(tmp_path / "config" / "settings.json")

    settings = store.load()

    assert settings == AppSettings()
    assert settings.start_at_login
    assert settings.listening_enabled
    assert settings.stt is None
    assert not settings.action_execution_enabled
    assert not settings.system_power_enabled
    assert settings.allowed_apps == ()
    assert settings.allowed_chat_apps == ()
    assert settings.allowed_window_apps == ()
    assert settings.allowed_close_apps == ()
    assert settings.wake_aliases == ()
    assert settings.app_spoken_aliases == ()
    assert not store.path.exists()


def test_selected_gpu_is_saved_without_claiming_it_is_available(tmp_path: Path) -> None:
    store = JsonSettingsStore(tmp_path / "settings.json")
    settings = AppSettings(
        microphone_device_key="pulse:USB microphone",
        stt=SttSelection(
            backend="whisper",
            model_path=tmp_path / "models" / "small.bin",
            language="en",
            device=DevicePreference.GPU,
        ),
        action_execution_enabled=True,
        allowed_apps=(AllowedApp("telegram", "org.telegram.desktop"),),
        allowed_chat_apps=("telegram",),
        wake_aliases=("kayrin", "کایرین من"),
    )

    store.save(settings)

    assert store.load() == settings
    assert json.loads(store.path.read_text(encoding="utf-8"))["schema_version"] == 11
    assert store.path.stat().st_mode & 0o077 == 0


def test_registered_app_aliases_round_trip_and_v9_starts_empty(tmp_path: Path) -> None:
    store = JsonSettingsStore(tmp_path / "settings.json")
    aliases = (
        AppSpokenAliases("org.example.Editor.desktop", ("ویرایشگر من", "My Editor")),
        AppSpokenAliases("other-platform-id", ("برنامهٔ دوم",)),
    )
    store.save(AppSettings(app_spoken_aliases=aliases))
    assert store.load().app_spoken_aliases == aliases

    document = json.loads(store.path.read_text(encoding="utf-8"))
    document["schema_version"] = 9
    del document["app_spoken_aliases"]
    del document["tts_enabled"]
    store.path.write_text(json.dumps(document), encoding="utf-8")
    assert store.load().app_spoken_aliases == ()


def test_registered_app_aliases_reject_invalid_or_duplicate_entries(
    tmp_path: Path,
) -> None:
    with pytest.raises(ValueError, match="unique short phrases"):
        AppSpokenAliases("editor.desktop", ("Editor", "EDITOR"))
    with pytest.raises(ValueError, match="registered app ID"):
        AppSpokenAliases("", ("Editor",))
    with pytest.raises(ValueError, match="unique short phrases"):
        AppSpokenAliases("editor.desktop", ("...",))
    item = AppSpokenAliases("editor.desktop", ("ویرایشگر",))
    with pytest.raises(ValueError, match="unique registered IDs"):
        AppSettings(app_spoken_aliases=(item, item))
    with pytest.raises(ValueError, match="unique registered IDs"):
        AppSettings(
            app_spoken_aliases=(
                item,
                AppSpokenAliases("other.desktop", ("ويرايشگر",)),
            )
        )

    store = JsonSettingsStore(tmp_path / "settings.json")
    store.save(AppSettings())
    document = json.loads(store.path.read_text(encoding="utf-8"))
    document["app_spoken_aliases"] = [
        {"platform_id": "editor.desktop", "aliases": ["One", "one"]}
    ]
    store.path.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(SettingsError, match="unique short phrases"):
        store.load()


def test_ocr_package_selection_round_trips_and_v8_uses_default(tmp_path: Path) -> None:
    store = JsonSettingsStore(tmp_path / "settings.json")
    selection = OcrSelection("tesseract", tmp_path / "ocr" / "alternate")
    store.save(AppSettings(ocr=selection))
    assert store.load().ocr == selection

    document = json.loads(store.path.read_text(encoding="utf-8"))
    document["schema_version"] = 8
    del document["ocr"]
    del document["app_spoken_aliases"]
    del document["tts_enabled"]
    store.path.write_text(json.dumps(document), encoding="utf-8")
    assert store.load().ocr is None


def test_local_tts_selection_round_trips_and_legacy_settings_use_system_voice(
    tmp_path: Path,
) -> None:
    store = JsonSettingsStore(tmp_path / "settings.json")
    tts = TtsSelection("kitten", tmp_path / "kitten", "3", 1.1, DevicePreference.GPU)
    store.save(AppSettings(tts=tts))
    assert store.load().tts == tts

    document = json.loads(store.path.read_text(encoding="utf-8"))
    document["schema_version"] = 6
    del document["tts"]
    del document["tts_languages"]
    del document["ocr"]
    del document["app_spoken_aliases"]
    del document["tts_enabled"]
    store.path.write_text(json.dumps(document), encoding="utf-8")
    assert store.load().tts == TtsSelection()


def test_voice_output_switch_round_trips_and_v10_defaults_to_on(tmp_path: Path) -> None:
    store = JsonSettingsStore(tmp_path / "settings.json")
    store.save(AppSettings(tts_enabled=False))
    assert not store.load().tts_enabled
    document = json.loads(store.path.read_text(encoding="utf-8"))
    document["schema_version"] = 10
    del document["tts_enabled"]
    store.path.write_text(json.dumps(document), encoding="utf-8")
    assert store.load().tts_enabled

    store.save(AppSettings())
    document = json.loads(store.path.read_text(encoding="utf-8"))
    document["tts_enabled"] = "false"
    store.path.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(SettingsError, match="tts_enabled must be a boolean"):
        store.load()


def test_tts_rejects_invalid_voice_and_gpu_system_voice(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="voice number"):
        TtsSelection("kitten", tmp_path, "8")
    with pytest.raises(ValueError, match="CPU-only"):
        TtsSelection(device=DevicePreference.GPU)


def test_unavailable_tts_adapter_preserves_choice_and_reports_it(
    tmp_path: Path,
) -> None:
    from kyrin.tts.runtime import validate_tts_selection

    store = JsonSettingsStore(tmp_path / "settings.json")
    choice = TtsSelection("futurevoice", tmp_path / "voice", "0")
    store.save(AppSettings(tts=choice))
    assert store.load().tts == choice
    with pytest.raises(ValueError, match="adapter is unavailable: futurevoice"):
        validate_tts_selection(choice)


def test_persian_tts_route_round_trips_and_v7_migrates(tmp_path: Path) -> None:
    store = JsonSettingsStore(tmp_path / "settings.json")
    persian = TtsLanguageRoute(
        "fa", TtsSelection("vits", tmp_path / "vits-piper-fa_IR", "0")
    )
    store.save(AppSettings(tts_languages=(persian,)))
    assert store.load().tts_languages == (persian,)
    document = json.loads(store.path.read_text(encoding="utf-8"))
    document["schema_version"] = 7
    del document["tts_languages"]
    del document["ocr"]
    del document["app_spoken_aliases"]
    del document["tts_enabled"]
    store.path.write_text(json.dumps(document), encoding="utf-8")
    assert store.load().tts_languages == ()


def test_command_model_selection_round_trips_and_old_schema_stays_off(
    tmp_path: Path,
) -> None:
    store = JsonSettingsStore(tmp_path / "settings.json")
    selection = CommandModelSelection(
        "ollama", "qwen3.5:4b", tmp_path / "models", DevicePreference.CPU
    )
    store.save(AppSettings(command_model=selection))
    assert store.load().command_model == selection
    document = json.loads(store.path.read_text(encoding="utf-8"))
    document["schema_version"] = 5
    del document["command_model"]
    del document["tts"]
    del document["tts_languages"]
    del document["ocr"]
    del document["app_spoken_aliases"]
    del document["tts_enabled"]
    store.path.write_text(json.dumps(document), encoding="utf-8")
    assert store.load().command_model is None


def test_corrupt_file_is_preserved_and_never_replaced_by_defaults(
    tmp_path: Path,
) -> None:
    store = JsonSettingsStore(tmp_path / "settings.json")
    contents = "{ broken settings"
    store.path.write_text(contents, encoding="utf-8")

    with pytest.raises(SettingsError, match="valid JSON"):
        store.load()

    assert store.path.read_text(encoding="utf-8") == contents


def test_unsupported_version_and_wrong_types_are_rejected(tmp_path: Path) -> None:
    store = JsonSettingsStore(tmp_path / "settings.json")
    store.save(AppSettings())
    document = json.loads(store.path.read_text(encoding="utf-8"))
    document["schema_version"] = 12
    store.path.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(SettingsError, match="schema version"):
        store.load()

    document["schema_version"] = 11
    document["listening_enabled"] = 1
    store.path.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(SettingsError, match="boolean"):
        store.load()

    document["listening_enabled"] = True
    document["unexpected"] = "value"
    store.path.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(SettingsError, match="missing or unknown"):
        store.load()


def test_duplicate_json_fields_cannot_change_action_permission(tmp_path: Path) -> None:
    store = JsonSettingsStore(tmp_path / "settings.json")
    store.path.write_text(
        '{"action_execution_enabled": false, "action_execution_enabled": true}',
        encoding="utf-8",
    )

    with pytest.raises(SettingsError, match="duplicate settings field"):
        store.load()


def test_failed_atomic_replace_keeps_previous_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = JsonSettingsStore(tmp_path / "settings.json")
    store.save(AppSettings())
    previous = store.path.read_bytes()

    def fail_replace(source: Path, target: Path) -> None:
        raise OSError("simulated disk error")

    monkeypatch.setattr(os, "replace", fail_replace)
    with pytest.raises(SettingsError, match="could not be saved"):
        store.save(replace(AppSettings(), listening_enabled=False))

    assert store.path.read_bytes() == previous
    assert list(tmp_path.glob(".settings-*.json")) == []


def test_duplicate_app_bindings_and_relative_models_are_invalid(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="duplicate"):
        AppSettings(
            allowed_apps=(
                AllowedApp("telegram", "org.telegram.desktop"),
                AllowedApp("telegram", "other.desktop"),
            )
        )
    with pytest.raises(ValueError, match="absolute"):
        SttSelection("whisper", Path("relative.bin"), "en")
    assert not (tmp_path / "relative.bin").exists()
    with pytest.raises(ValueError, match="chat permission"):
        AppSettings(allowed_chat_apps=("telegram",))
    with pytest.raises(ValueError, match="wake aliases"):
        AppSettings(wake_aliases=("kayrin", "KAYRIN"))


def test_version_one_settings_migrate_with_chat_permission_off(tmp_path: Path) -> None:
    store = JsonSettingsStore(tmp_path / "settings.json")
    store.save(AppSettings(allowed_apps=(AllowedApp("telegram", "telegram.desktop"),)))
    document = json.loads(store.path.read_text(encoding="utf-8"))
    document["schema_version"] = 1
    del document["command_model"]
    del document["tts"]
    del document["tts_languages"]
    del document["ocr"]
    del document["app_spoken_aliases"]
    del document["tts_enabled"]
    del document["allowed_chat_apps"]
    del document["wake_aliases"]
    del document["allowed_window_apps"]
    del document["allowed_close_apps"]
    del document["system_power_enabled"]
    store.path.write_text(json.dumps(document), encoding="utf-8")

    loaded = store.load()

    assert loaded.allowed_apps == (AllowedApp("telegram", "telegram.desktop"),)
    assert loaded.allowed_chat_apps == ()
    assert loaded.wake_aliases == ()


def test_version_two_settings_migrate_with_no_custom_wake_aliases(
    tmp_path: Path,
) -> None:
    store = JsonSettingsStore(tmp_path / "settings.json")
    store.save(AppSettings(wake_aliases=("kayrin",)))
    document = json.loads(store.path.read_text(encoding="utf-8"))
    document["schema_version"] = 2
    del document["command_model"]
    del document["tts"]
    del document["tts_languages"]
    del document["ocr"]
    del document["app_spoken_aliases"]
    del document["tts_enabled"]
    del document["wake_aliases"]
    del document["allowed_window_apps"]
    del document["allowed_close_apps"]
    del document["system_power_enabled"]
    store.path.write_text(json.dumps(document), encoding="utf-8")

    assert store.load().wake_aliases == ()


def test_legacy_settings_do_not_enable_window_or_close_permissions(
    tmp_path: Path,
) -> None:
    store = JsonSettingsStore(tmp_path / "settings.json")
    store.save(AppSettings(allowed_apps=(AllowedApp("telegram", "telegram.desktop"),)))
    document = json.loads(store.path.read_text(encoding="utf-8"))
    document["schema_version"] = 3
    del document["command_model"]
    del document["tts"]
    del document["tts_languages"]
    del document["ocr"]
    del document["app_spoken_aliases"]
    del document["tts_enabled"]
    del document["allowed_window_apps"]
    del document["allowed_close_apps"]
    del document["system_power_enabled"]
    store.path.write_text(json.dumps(document), encoding="utf-8")

    loaded = store.load()
    assert loaded.allowed_window_apps == ()
    assert loaded.allowed_close_apps == ()
    assert not loaded.system_power_enabled


def test_version_four_never_enables_power_permission(tmp_path: Path) -> None:
    store = JsonSettingsStore(tmp_path / "settings.json")
    store.save(AppSettings(system_power_enabled=True))
    document = json.loads(store.path.read_text(encoding="utf-8"))
    document["schema_version"] = 4
    del document["command_model"]
    del document["tts"]
    del document["tts_languages"]
    del document["ocr"]
    del document["app_spoken_aliases"]
    del document["tts_enabled"]
    del document["system_power_enabled"]
    store.path.write_text(json.dumps(document), encoding="utf-8")
    assert not store.load().system_power_enabled


def test_linux_settings_path_uses_absolute_config_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    assert linux_settings_path() == tmp_path / "kyrin" / "settings.json"

    monkeypatch.setenv("XDG_CONFIG_HOME", "relative-config")
    assert linux_settings_path() == Path.home() / ".config/kyrin/settings.json"
