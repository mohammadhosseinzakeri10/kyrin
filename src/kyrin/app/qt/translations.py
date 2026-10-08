"""Small, offline UI-language packs independent of the speech language."""

import json
import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path

ENGLISH: dict[str, str] = {
    "window_title": "KYRIN — Control Center",
    "dashboard": "Dashboard",
    "audio": "Audio Input",
    "recognition": "Speech Recognition",
    "actions": "Desktop Actions",
    "preferences": "Preferences",
    "welcome": "Welcome to KYRIN",
    "welcome_caption": "Your workspace, one voice away.",
    "scene_hint": "A quiet window into the cosmos",
    "status": "System status",
    "feedback_default": "Responses and errors will appear here.",
    "audio_heading": "Audio input",
    "audio_caption": "Choose the microphone KYRIN listens to.",
    "microphone": "Microphone",
    "default_microphone": "System default microphone",
    "missing_microphone": "Previous microphone (unavailable)",
    "recognition_heading": "Speech recognition",
    "recognition_caption": "Select an installed offline model and processing device.",
    "backend": "Engine",
    "model": "Installed model",
    "browse": "Browse…",
    "speech_language": "Speech language code",
    "device": "Run model on",
    "auto": "Automatic",
    "cpu": "CPU",
    "gpu": "GPU",
    "save": "Save changes",
    "start": "Start listening",
    "stop": "Stop listening",
    "quit": "Quit KYRIN",
    "actions_on": "Desktop actions enabled",
    "actions_off": "Desktop actions disabled",
    "allowed_apps": "allowed apps",
    "actions_heading": "Desktop actions",
    "actions_caption": "Choose exactly which installed apps KYRIN may open.",
    "enable_actions": "Allow KYRIN to open the selected apps",
    "actions_search": "Search installed apps…",
    "action_select_one": "Select at least one app before enabling desktop actions.",
    "app_unavailable": "Unavailable",
    "preferences_heading": "Preferences",
    "preferences_caption": "Choose the language of the control center.",
    "interface_language": "Interface language",
    "start_at_login": "Start KYRIN when I sign in",
    "apply_startup": "Apply startup setting",
    "startup_saved": "Login startup setting saved.",
    "startup_unavailable": "Installed KYRIN launcher is unavailable.",
    "import_language": "Add language pack…",
    "language_help": "Language packs can be added here without changing code.",
    "language_added": "Language pack added.",
    "ui_saved": "Interface preferences saved.",
    "state_stopped": "Stopped",
    "state_paused": "Listening is off",
    "state_setup": "Speech model setup required",
    "state_starting": "Starting",
    "state_running": "Running",
    "state_stopping": "Stopping",
    "state_error": "Error",
    "heard": "Heard",
    "saved": "Settings saved.",
    "stopping_old": "Stopping the previous session before applying changes…",
    "wait_stop": "Please wait for the session to stop.",
    "save_first": "Save microphone and model changes first.",
    "choose_model": "Select and save a speech model first.",
    "previous_failed": "Previous session failed; new settings were not applied.",
    "error_device": "The selected processor is unavailable for this model.",
    "error_microphone": "Selected microphone unavailable. Check audio input.",
    "error_file": "The model file or speech tool was not found. Check its path.",
    "error_settings": "Settings failed to load or save. Original file unchanged.",
    "error_generic": "KYRIN encountered an error",
    "path_absolute": "The model path must be absolute.",
    "vosk_missing": "The Vosk model directory was not found.",
    "whisper_missing": "The Whisper model file was not found.",
    "whisper_server_missing": "The local whisper-server is not available.",
    "vosk_directory": "Select a Vosk model directory",
    "whisper_file": "Select a Whisper model file",
    "language_file": "Select a KYRIN language pack",
}

_NEW_ACTION_KEYS = frozenset(
    {
        "actions",
        "actions_heading",
        "actions_caption",
        "enable_actions",
        "actions_search",
        "action_select_one",
        "app_unavailable",
    }
)

_LOCALE = re.compile(r"^[a-z]{2,3}(?:-[A-Z]{2})?$")


class TranslationError(ValueError):
    """A language pack or UI preferences file is invalid."""


@dataclass(frozen=True, slots=True)
class UiPreferences:
    locale: str = "en"


class UiTranslations:
    """Install complete JSON catalogs into the user's private config folder."""

    def __init__(self, directory: Path) -> None:
        if not directory.is_absolute():
            raise ValueError("UI config directory must be absolute")
        self.directory = directory
        self.load_error: TranslationError | None = None
        try:
            preferences = self._load_preferences()
            _, strings = self._catalog(preferences.locale)
        except TranslationError as error:
            # Keep the damaged file untouched. The English UI can still open,
            # explain the problem, and let the user explicitly save a choice.
            self.load_error = error
            self.preferences = UiPreferences()
            self._strings = ENGLISH
        else:
            self.preferences = preferences
            self._strings = strings

    def _load_preferences(self) -> UiPreferences:
        path = self.directory / "ui.json"
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return UiPreferences()
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise TranslationError("UI preferences could not be read") from exc
        if not isinstance(data, dict) or set(data) != {"locale"}:
            raise TranslationError("UI preferences have invalid fields")
        locale = data["locale"]
        if not isinstance(locale, str) or not _LOCALE.fullmatch(locale):
            raise TranslationError("Invalid UI locale")
        return UiPreferences(locale)

    def _catalog(self, locale: str) -> tuple[str, dict[str, str]]:
        if locale == "en":
            return "English", ENGLISH
        if not _LOCALE.fullmatch(locale):
            raise TranslationError("Invalid UI locale")
        path = self.directory / "languages" / f"{locale}.json"
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise TranslationError(f"Language pack {locale} could not be read") from exc
        if (
            not isinstance(data, dict)
            or set(data) != {"locale", "name", "strings"}
            or data["locale"] != locale
            or not isinstance(data["name"], str)
            or not data["name"].strip()
            or not isinstance(data["strings"], dict)
            or set(data["strings"])
            not in (set(ENGLISH), set(ENGLISH) - _NEW_ACTION_KEYS)
            or not all(
                isinstance(value, str) and value.strip()
                for value in data["strings"].values()
            )
        ):
            raise TranslationError("Language pack must contain every UI string")
        return data["name"], {**ENGLISH, **data["strings"]}

    def text(self, key: str) -> str:
        return self._strings[key]

    def languages(self) -> tuple[tuple[str, str], ...]:
        languages = [("en", "English")]
        for path in sorted((self.directory / "languages").glob("*.json")):
            try:
                name, _ = self._catalog(path.stem)
            except TranslationError:
                continue
            languages.append((path.stem, name))
        return tuple(languages)

    def import_pack(self, source: Path) -> str:
        try:
            data = json.loads(source.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise TranslationError("Language pack could not be read") from exc
        if not isinstance(data, dict):
            raise TranslationError("Language pack must be a JSON object")
        locale = data.get("locale")
        if (
            not isinstance(locale, str)
            or locale == "en"
            or not _LOCALE.fullmatch(locale)
        ):
            raise TranslationError("Language pack has an invalid locale")
        # Validate before writing anything.
        if (
            set(data) != {"locale", "name", "strings"}
            or not isinstance(data["name"], str)
            or not data["name"].strip()
            or not isinstance(data["strings"], dict)
            or set(data["strings"]) != set(ENGLISH)
            or not all(
                isinstance(value, str) and value.strip()
                for value in data["strings"].values()
            )
        ):
            raise TranslationError("Language pack must contain every UI string")
        self._atomic_json(self.directory / "languages" / f"{locale}.json", data)
        if locale == self.preferences.locale:
            self._strings = data["strings"]
        return locale

    def save(self, preferences: UiPreferences) -> None:
        _, strings = self._catalog(preferences.locale)
        self._atomic_json(
            self.directory / "ui.json",
            {"locale": preferences.locale},
        )
        self.preferences = preferences
        self._strings = strings
        self.load_error = None

    @staticmethod
    def _atomic_json(path: Path, data: object) -> None:
        temporary: Path | None = None
        try:
            path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=path.parent,
                prefix=".ui-",
                suffix=".json",
                delete=False,
            ) as stream:
                temporary = Path(stream.name)
                json.dump(data, stream, ensure_ascii=False, indent=2)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
        except OSError as exc:
            raise TranslationError("UI preferences could not be saved") from exc
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
