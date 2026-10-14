"""Versioned JSON persistence for application preferences, never runtime state."""

import json
import os
import tempfile
from pathlib import Path
from typing import cast

from kyrin.app.settings import (
    AllowedApp,
    AppSettings,
    CommandModelSelection,
    OcrSelection,
    SttSelection,
    TtsLanguageRoute,
    TtsSelection,
)
from kyrin.stt.device import DevicePreference

SCHEMA_VERSION = 9


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


def _parse_tts(value: object, location: str) -> TtsSelection:
    selected = _object(
        value, {"backend", "model_path", "voice", "speed", "device"}, location
    )
    raw_path = selected["model_path"]
    if raw_path is not None:
        raw_path = _string(raw_path, f"{location}.model_path")
    raw_speed = selected["speed"]
    if type(raw_speed) not in (int, float):
        raise SettingsError(f"{location}.speed must be a number")
    try:
        return TtsSelection(
            backend=_string(selected["backend"], f"{location}.backend"),
            model_path=Path(raw_path) if isinstance(raw_path, str) else None,
            voice=_string(selected["voice"], f"{location}.voice"),
            speed=float(cast("int | float", raw_speed)),
            device=DevicePreference(_string(selected["device"], f"{location}.device")),
        )
    except ValueError as exc:
        raise SettingsError(str(exc)) from exc


def _tts_document(selection: TtsSelection) -> dict[str, object]:
    return {
        "backend": selection.backend,
        "model_path": str(selection.model_path) if selection.model_path else None,
        "voice": selection.voice,
        "speed": selection.speed,
        "device": selection.device.value,
    }


def _parse_settings(document: object) -> AppSettings:
    if (
        not isinstance(document, dict)
        or type(document.get("schema_version")) is not int
    ):
        raise SettingsError("unsupported settings schema version")
    version = document["schema_version"]
    if version not in range(1, SCHEMA_VERSION + 1):
        raise SettingsError("unsupported settings schema version")
    fields = {
        "schema_version",
        "listening_enabled",
        "start_at_login",
        "microphone_device_key",
        "stt",
        "action_execution_enabled",
        "allowed_apps",
    }
    if version >= 2:
        fields.add("allowed_chat_apps")
    if version >= 3:
        fields.add("wake_aliases")
    if version >= 4:
        fields.update({"allowed_window_apps", "allowed_close_apps"})
    if version >= 5:
        fields.add("system_power_enabled")
    if version >= 6:
        fields.add("command_model")
    if version >= 7:
        fields.add("tts")
    if version >= 8:
        fields.add("tts_languages")
    if version >= 9:
        fields.add("ocr")
    root = _object(document, fields, "settings")
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

    command_model: CommandModelSelection | None = None
    raw_command_model = root["command_model"] if version >= 6 else None
    if raw_command_model is not None:
        selected_command = _object(
            raw_command_model,
            {"backend", "model", "store_path", "device"},
            "command_model",
        )
        try:
            command_device = DevicePreference(
                _string(selected_command["device"], "command_model.device")
            )
        except ValueError as exc:
            raise SettingsError(
                "command_model.device must be auto, cpu, or gpu"
            ) from exc
        command_model = CommandModelSelection(
            backend=_string(selected_command["backend"], "command_model.backend"),
            model=_string(selected_command["model"], "command_model.model"),
            store_path=Path(
                _string(selected_command["store_path"], "command_model.store_path")
            ),
            device=command_device,
        )

    ocr: OcrSelection | None = None
    raw_ocr = root["ocr"] if version >= 9 else None
    if raw_ocr is not None:
        selected_ocr = _object(raw_ocr, {"backend", "model_path"}, "ocr")
        ocr = OcrSelection(
            backend=_string(selected_ocr["backend"], "ocr.backend"),
            model_path=Path(_string(selected_ocr["model_path"], "ocr.model_path")),
        )

    tts = TtsSelection()
    if version >= 7:
        tts = _parse_tts(root["tts"], "tts")
    tts_languages: tuple[TtsLanguageRoute, ...] = ()
    if version >= 8:
        raw_routes = root["tts_languages"]
        if not isinstance(raw_routes, list):
            raise SettingsError("tts_languages must be a list")
        routes: list[TtsLanguageRoute] = []
        for index, raw_route in enumerate(raw_routes):
            location = f"tts_languages[{index}]"
            item = _object(raw_route, {"language", "selection"}, location)
            try:
                routes.append(
                    TtsLanguageRoute(
                        _string(item["language"], f"{location}.language"),
                        _parse_tts(item["selection"], f"{location}.selection"),
                    )
                )
            except ValueError as exc:
                raise SettingsError(str(exc)) from exc
        tts_languages = tuple(routes)

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
    raw_chat_apps = root["allowed_chat_apps"] if version >= 2 else []
    if not isinstance(raw_chat_apps, list):
        raise SettingsError("allowed_chat_apps must be a list")
    chat_apps = tuple(
        _string(app_id, f"allowed_chat_apps[{index}]")
        for index, app_id in enumerate(raw_chat_apps)
    )
    raw_wake_aliases = root["wake_aliases"] if version >= 3 else []
    if not isinstance(raw_wake_aliases, list):
        raise SettingsError("wake_aliases must be a list")
    wake_aliases = tuple(
        _string(alias, f"wake_aliases[{index}]")
        for index, alias in enumerate(raw_wake_aliases)
    )
    window_apps: tuple[str, ...] = ()
    close_apps: tuple[str, ...] = ()
    if version >= 4:
        raw_window_apps = root["allowed_window_apps"]
        raw_close_apps = root["allowed_close_apps"]
        if not isinstance(raw_window_apps, list):
            raise SettingsError("allowed_window_apps must be a list")
        if not isinstance(raw_close_apps, list):
            raise SettingsError("allowed_close_apps must be a list")
        window_apps = tuple(
            _string(app_id, f"allowed_window_apps[{index}]")
            for index, app_id in enumerate(raw_window_apps)
        )
        close_apps = tuple(
            _string(app_id, f"allowed_close_apps[{index}]")
            for index, app_id in enumerate(raw_close_apps)
        )
    try:
        return AppSettings(
            listening_enabled=_boolean(root["listening_enabled"], "listening_enabled"),
            start_at_login=_boolean(root["start_at_login"], "start_at_login"),
            microphone_device_key=microphone,
            stt=stt,
            command_model=command_model,
            ocr=ocr,
            tts=tts,
            tts_languages=tts_languages,
            action_execution_enabled=_boolean(
                root["action_execution_enabled"], "action_execution_enabled"
            ),
            system_power_enabled=(
                _boolean(root["system_power_enabled"], "system_power_enabled")
                if version >= 5
                else False
            ),
            allowed_apps=tuple(apps),
            allowed_chat_apps=chat_apps,
            allowed_window_apps=window_apps,
            allowed_close_apps=close_apps,
            wake_aliases=wake_aliases,
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
        "command_model": (
            None
            if settings.command_model is None
            else {
                "backend": settings.command_model.backend,
                "model": settings.command_model.model,
                "store_path": str(settings.command_model.store_path),
                "device": settings.command_model.device.value,
            }
        ),
        "ocr": (
            None
            if settings.ocr is None
            else {
                "backend": settings.ocr.backend,
                "model_path": str(settings.ocr.model_path),
            }
        ),
        "tts": _tts_document(settings.tts),
        "tts_languages": [
            {"language": route.language, "selection": _tts_document(route.selection)}
            for route in settings.tts_languages
        ],
        "action_execution_enabled": settings.action_execution_enabled,
        "system_power_enabled": settings.system_power_enabled,
        "allowed_apps": [
            {"app_id": app.app_id, "desktop_id": app.desktop_id}
            for app in settings.allowed_apps
        ],
        "allowed_chat_apps": list(settings.allowed_chat_apps),
        "allowed_window_apps": list(settings.allowed_window_apps),
        "allowed_close_apps": list(settings.allowed_close_apps),
        "wake_aliases": list(settings.wake_aliases),
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
