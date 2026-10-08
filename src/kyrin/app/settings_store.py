"""Versioned JSON persistence for application preferences, never runtime state."""

import json
import os
import tempfile
from pathlib import Path
from typing import cast

from kyrin.app.settings import AllowedApp, AppSettings, SttSelection
from kyrin.stt.device import DevicePreference

SCHEMA_VERSION = 1


class SettingsError(ValueError):
    """A settings file could not be read, validated, or safely written."""


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    item: dict[str, object] = {}
    for key, value in pairs:
        if key in item:
            raise SettingsError(f"duplicate settings field: {key}")
        item[key] = value
    return item


def linux_settings_path() -> Path:
    """Choose a user config location without accessing or creating it."""
    configured = os.environ.get("XDG_CONFIG_HOME")
    root = Path(configured) if configured else Path.home() / ".config"
    if not root.is_absolute():
        root = Path.home() / ".config"
    return root / "kyrin" / "settings.json"


def _object(value: object, fields: set[str], location: str) -> dict[str, object]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise SettingsError(f"{location} must be an object")
    item = cast("dict[str, object]", value)
    if set(item) != fields:
        raise SettingsError(f"{location} has missing or unknown fields")
    return item


def _boolean(value: object, location: str) -> bool:
    if type(value) is not bool:
        raise SettingsError(f"{location} must be a boolean")
    return value


def _string(value: object, location: str) -> str:
    if not isinstance(value, str):
        raise SettingsError(f"{location} must be a string")
    return value


def _parse_settings(document: object) -> AppSettings:
    root = _object(
        document,
        {
            "schema_version",
            "listening_enabled",
            "start_at_login",
            "microphone_device_key",
            "stt",
            "action_execution_enabled",
            "allowed_apps",
        },
        "settings",
    )
    if type(root["schema_version"]) is not int or root["schema_version"] != 1:
        raise SettingsError("unsupported settings schema version")
    microphone = root["microphone_device_key"]
    if microphone is not None:
        microphone = _string(microphone, "microphone_device_key")

    raw_stt = root["stt"]
    stt: SttSelection | None = None
    if raw_stt is not None:
        selected = _object(
            raw_stt, {"backend", "model_path", "language", "device"}, "stt"
        )
        device_name = _string(selected["device"], "stt.device")
        try:
            device = DevicePreference(device_name)
        except ValueError as exc:
            raise SettingsError("stt.device must be auto, cpu, or gpu") from exc
        stt = SttSelection(
            backend=_string(selected["backend"], "stt.backend"),
            model_path=Path(_string(selected["model_path"], "stt.model_path")),
            language=_string(selected["language"], "stt.language"),
            device=device,
        )

    raw_apps = root["allowed_apps"]
    if not isinstance(raw_apps, list):
        raise SettingsError("allowed_apps must be a list")
    apps: list[AllowedApp] = []
    for index, raw_app in enumerate(raw_apps):
        item = _object(raw_app, {"app_id", "desktop_id"}, f"allowed_apps[{index}]")
        apps.append(
            AllowedApp(
                _string(item["app_id"], f"allowed_apps[{index}].app_id"),
                _string(item["desktop_id"], f"allowed_apps[{index}].desktop_id"),
            )
        )
    try:
        return AppSettings(
            listening_enabled=_boolean(root["listening_enabled"], "listening_enabled"),
            start_at_login=_boolean(root["start_at_login"], "start_at_login"),
            microphone_device_key=microphone,
            stt=stt,
            action_execution_enabled=_boolean(
                root["action_execution_enabled"], "action_execution_enabled"
            ),
            allowed_apps=tuple(apps),
        )
    except ValueError as exc:
        raise SettingsError(str(exc)) from exc


def _document(settings: AppSettings) -> dict[str, object]:
    stt = settings.stt
    return {
        "schema_version": SCHEMA_VERSION,
        "listening_enabled": settings.listening_enabled,
        "start_at_login": settings.start_at_login,
        "microphone_device_key": settings.microphone_device_key,
        "stt": (
            None
            if stt is None
            else {
                "backend": stt.backend,
                "model_path": str(stt.model_path),
                "language": stt.language,
                "device": stt.device.value,
            }
        ),
        "action_execution_enabled": settings.action_execution_enabled,
        "allowed_apps": [
            {"app_id": app.app_id, "desktop_id": app.desktop_id}
            for app in settings.allowed_apps
        ],
    }


class JsonSettingsStore:
    """Read and atomically replace one injected file; never touch login setup."""

    def __init__(self, path: Path) -> None:
        if not path.is_absolute():
            raise ValueError("settings path must be absolute")
        self.path = path

    def load(self) -> AppSettings:
        try:
            contents = self.path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return AppSettings()
        except (OSError, UnicodeError) as exc:
            raise SettingsError("settings file could not be read") from exc
        try:
            document: object = json.loads(contents, object_pairs_hook=_unique_object)
            return _parse_settings(document)
        except json.JSONDecodeError as exc:
            raise SettingsError("settings file is not valid JSON") from exc
        except ValueError as exc:
            if isinstance(exc, SettingsError):
                raise
            raise SettingsError(str(exc)) from exc

    def save(self, settings: AppSettings) -> None:
        if not isinstance(settings, AppSettings):
            raise TypeError("settings must be AppSettings")
        temporary: Path | None = None
        try:
            self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=self.path.parent,
                prefix=".settings-",
                suffix=".json",
                delete=False,
            ) as output:
                temporary = Path(output.name)
                json.dump(_document(settings), output, ensure_ascii=False, indent=2)
                output.write("\n")
                output.flush()
                os.fsync(output.fileno())
            os.replace(temporary, self.path)
            temporary = None
        except OSError as exc:
            raise SettingsError("settings file could not be saved") from exc
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
