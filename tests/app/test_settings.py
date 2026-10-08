"""Saved preferences are validated without reading the owner's home folder."""

import json
import os
from dataclasses import replace
from pathlib import Path

import pytest

from kyrin.app.settings import AllowedApp, AppSettings, SttSelection
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
    assert settings.allowed_apps == ()
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
    )

    store.save(settings)

    assert store.load() == settings
    assert json.loads(store.path.read_text(encoding="utf-8"))["schema_version"] == 1
    assert store.path.stat().st_mode & 0o077 == 0


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
    document["schema_version"] = 2
    store.path.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(SettingsError, match="schema version"):
        store.load()

    document["schema_version"] = 1
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


def test_linux_settings_path_uses_absolute_config_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    assert linux_settings_path() == tmp_path / "kyrin" / "settings.json"

    monkeypatch.setenv("XDG_CONFIG_HOME", "relative-config")
    assert linux_settings_path() == Path.home() / ".config/kyrin/settings.json"
