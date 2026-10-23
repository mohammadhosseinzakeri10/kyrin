"""Small, offline UI-language packs independent of the speech language."""

import json
import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from string import Formatter

from PySide6.QtCore import QLocale

from kyrin.app.qt.locale_fa import PERSIAN

ENGLISH: dict[str, str] = {
    "window_title": "KYRIN — Control Center",
    "dashboard": "Dashboard",
    "audio": "Audio Input",
    "recognition": "Speech Recognition",
    "models": "Model Library",
    "command_models": "Command Understanding",
    "tts": "Voice Output",
    "tts_heading": "Voice output",
    "tts_enabled": "Play spoken responses",
    "tts_caption": (
        "Choose an installed offline voice. KYRIN never downloads voice models. "
        "Place a supported extracted model in your local TTS folder or browse "
        "to it; KYRIN detects its engine. Test the current settings before saving."
    ),
    "tts_engine": "Engine",
    "tts_installed": "Installed local models",
    "tts_select_installed": "Select a local model…",
    "tts_refresh": "Refresh",
    "tts_system": "System voice (Speech Dispatcher)",
    "tts_folder": "Local model folder",
    "tts_voice": "Voice",
    "tts_speed": "Speaking speed",
    "tts_device": "Run voice on",
    "tts_add_language": "Add language voice…",
    "tts_remove_language": "Remove selected language",
    "tts_language_code": "Language code (for example fa, de, fr)",
    "tts_sample_text": "Test phrase in this language",
    "tts_select_folder": "Select an extracted TTS model folder",
    "tts_preview": "Test current voice settings",
    "tts_preview_started": "Playing a short sample with the current settings…",
    "tts_preview_unavailable": "Voice preview is unavailable.",
    "command_models_heading": "Command understanding",
    "command_models_caption": (
        "Choose a local language model for commands the fast rules cannot resolve. "
        "Model output is checked against the original words and action permissions. "
        "CPU may take much longer than GPU."
    ),
    "command_models_rules": "Fast rules only (default)",
    "command_models_engine": "Engine",
    "command_models_store": "Local model store",
    "command_models_device": "Run model on",
    "command_models_refresh": "Refresh installed models",
    "command_models_store_title": "Select an Ollama model store",
    "command_models_found": "{count} complete local models found.",
    "command_models_missing_store": "Choose an absolute local Ollama model store.",
    "command_models_choose": "Select an installed command model first.",
    "actions": "Desktop Actions",
    "screen": "Screen Access",
    "preferences": "Preferences",
    "welcome": "Welcome to KYRIN",
    "welcome_caption": "Your workspace, one voice away.",
    "scene_hint": "Created by KAILARIN",
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
    "speech_language_help": (
        "Use a language code such as en or fa. Whisper multilingual models also "
        "accept auto; Omnilingual LLM models work better with a language code; "
        "Vosk requires a specific language model."
    ),
    "omnilingual_directory": "Select an Omnilingual ASR model folder",
    "omnilingual_runtime_missing": "Omnilingual ASR runtime is not installed.",
    "vosk_language_required": "Vosk needs a specific language code, such as en.",
    "wake_aliases": "Other spellings of KYRIN (comma-separated)",
    "device": "Run model on",
    "auto": "Automatic",
    "cpu": "CPU",
    "gpu": "GPU",
    "device_actual": "Active STT device",
    "device_actual_pending": "Active STT device: waiting for session",
    "diagnostics_heading": "Recent speech decisions (this session only)",
    "diagnostics_clear": "Clear speech diagnostics",
    "diagnostics_decision": "Interpreted command",
    "diagnostics_no_command": "No action requested",
    "diagnostics_reason": "Reason or clarification",
    "diagnostics_result": "Action result",
    "models_heading": "Speech model library",
    "models_caption": (
        "Browse all installed models, or filter by CPU and GPU compatibility. "
        "Whisper weights can appear in both views without a second copy."
    ),
    "models_all": "All models",
    "models_cpu": "CPU models",
    "models_gpu": "GPU models",
    "models_language": "Whisper: auto or code; Vosk: model language code",
    "models_import_cpu": "Add model for CPU…",
    "models_import_gpu": "Add model for GPU…",
    "models_use": "Use selected model",
    "models_empty": "No models in this view yet.",
    "models_external": "Current external model",
    "models_unavailable": "The model library is unavailable.",
    "models_vosk_cpu": "Vosk currently supports CPU only.",
    "models_language_required": "Enter a language code before adding a model.",
    "models_vosk_language_mismatch": (
        "This Vosk folder appears to be for {hint}. Enter {hint} as its language code."
    ),
    "models_importing": "Adding model to your library…",
    "models_imported": "Model added. Select it and choose Use selected model.",
    "models_reused_language": (
        "These Whisper weights are already installed. Select the model, then "
        "set your preferred language in Speech Recognition before saving."
    ),
    "models_select_first": "Select a model from this list first.",
    "models_gpu_unavailable": "GPU runtime is not installed for this engine.",
    "models_cpu_unavailable": "CPU runtime is not installed for this engine.",
    "models_selected": "Model selected. Save changes to apply it.",
    "save": "Save changes",
    "start": "Start listening",
    "stop": "Stop listening",
    "microphone_off": "Turn microphone off",
    "voice_started": "Listening to commands.",
    "voice_standby": "Standby. Say Start listening to resume.",
    "voice_off": "Microphone is fully off.",
    "voice_turning_off": "Turning the microphone off…",
    "quit": "Quit KYRIN",
    "actions_on": "Desktop actions enabled",
    "actions_off": "Desktop actions disabled",
    "allowed_apps": "allowed apps",
    "actions_heading": "Desktop actions",
    "actions_caption": "Choose which installed apps KYRIN may control.",
    "enable_actions": "Enable the selected desktop actions",
    "allow_telegram_chats": (
        "Allow KYRIN to open chats in Telegram (no message sending)"
    ),
    "remember_telegram_pointer": (
        "Remember keyboard and mouse access for Telegram chats"
    ),
    "telegram_pointer_grant_now": "Set up Telegram control access now…",
    "telegram_pointer_not_ready": (
        "No saved control grant. Save these settings, then set up access here."
    ),
    "telegram_pointer_ready": (
        "A control grant is saved. The system may revoke it later."
    ),
    "telegram_pointer_grant_running": "Confirm the system's Remote Desktop request…",
    "telegram_pointer_grant_done": "Telegram keyboard and mouse access is saved.",
    "telegram_pointer_grant_failed": "Control access was not saved. Try again here.",
    "telegram_pointer_save_first": "Save Telegram chat and control settings first.",
    "allow_desktop_scroll": "Allow scrolling in the focused desktop app",
    "desktop_scroll_grant_now": "Set up desktop scroll access now…",
    "desktop_scroll_not_ready": (
        "No saved scroll access. Save settings, then set up access here."
    ),
    "desktop_scroll_ready": "Desktop scroll access is saved.",
    "desktop_scroll_running": "Confirm the system's Remote Desktop request…",
    "desktop_scroll_done": "Desktop scroll access is saved.",
    "desktop_scroll_failed": "Scroll access was not saved. Try again here.",
    "desktop_scroll_save_first": "Save desktop scroll settings first.",
    "allow_desktop_control": "Allow clicking visible controls in the focused app",
    "desktop_control_grant_now": "Set up desktop click access now…",
    "desktop_control_not_ready": (
        "Click access needs a separate one-time Remote Desktop grant. "
        "Save settings, then press the setup button below."
    ),
    "desktop_control_ready": "Desktop click access is saved.",
    "desktop_control_running": "Confirm the system's Remote Desktop request…",
    "desktop_control_done": "Desktop click access is saved.",
    "desktop_control_failed": "Click access was not saved. Try again here.",
    "desktop_control_save_first": "Save desktop click settings first.",
    "allow_window_controls": (
        "Allow KYRIN to restore, minimize, maximize, or fullscreen selected apps"
    ),
    "allow_window_close": "Allow KYRIN to close a window of selected apps",
    "allow_system_power": "Allow two-step system power requests (off by default)",
    "actions_search": "Search installed apps…",
    "app_spoken_aliases": "Other spoken names for the selected app",
    "app_spoken_aliases_placeholder": "Separate names with commas",
    "app_spoken_aliases_help": (
        "Names help recognition; they do not grant permission to control an app. "
        "Choose any listed app, including an unchecked one."
    ),
    "actions_select_visible": "Select all shown",
    "actions_clear_visible": "Clear shown",
    "actions_selected": "selected",
    "action_select_one": "Select at least one app or enable system power requests.",
    "app_unavailable": "Unavailable",
    "screen_heading": "Screen access",
    "screen_caption": (
        "Allow KYRIN to read the active window on request. GNOME asks once and "
        "remembers your choice until you turn it off here. No image is saved."
    ),
    "screen_enable": "Remember screen access",
    "screen_active": "Screen access is active. Turn this off to revoke it now.",
    "screen_off": "Screen access is off.",
    "screen_waiting": "Waiting for GNOME permission…",
    "screen_unavailable": (
        "Screen access is unavailable. Check the GNOME extension or restart KYRIN "
        "if another process owns its session name."
    ),
    "screen_read": "Read text in the active window",
    "screen_read_clear": "Clear screen text",
    "screen_ocr_model": "Local OCR model",
    "screen_ocr_browse": "Browse OCR folder…",
    "screen_ocr_hint": (
        "Choose a ready local Tesseract or PaddleOCR model, then save to switch. "
        "PaddleOCR-VL reads text and positions but has no confidence score; "
        "screen actions that require confidence will stop safely."
    ),
    "screen_read_hint": (
        "Read a snapshot when you need it. Visible text stays in memory."
    ),
    "screen_reading": "Reading the active window…",
    "screen_ocr_unavailable": "The selected offline OCR runtime is unavailable.",
    "screen_capture_unavailable": "The active window could not be captured.",
    "screen_window_changed": "The active window changed. Read it again.",
    "screen_ocr_failed": "The screen text could not be read.",
    "screen_no_text": "No readable text was found in that window.",
    "screen_read_result": "Snapshot from {app_id} (process {pid}).",
    "screen_read_truncated": (
        "Snapshot from {app_id} (process {pid}); showing the first 2,000 characters."
    ),
    "screen_document_heading": "Experimental document OCR",
    "screen_document_hint": (
        "Read the active window with a separate offline model. Save Changes remembers "
        "the document model and CPU/GPU choice. Clicking Read captures the "
        "KYRIN window if it is in front. This can take minutes on CPU. Results "
        "are text only and never used to click or run commands."
    ),
    "screen_document_device": "Document model compute device",
    "screen_document_device_auto": "Auto (GPU if available)",
    "screen_document_device_cpu": "CPU",
    "screen_document_device_gpu": "GPU (CUDA required)",
    "screen_document_gpu_unavailable": (
        "CUDA GPU is unavailable for this document model. "
        "Choose CPU or install its CUDA runtime."
    ),
    "screen_document_gpu_memory": (
        "The GPU ran out of memory while reading this window. "
        "Close other GPU programs or choose CPU."
    ),
    "screen_document_read": "Read with selected document model",
    "screen_document_clear": "Clear document text",
    "screen_document_ready": "Choose a model to compare its text output.",
    "screen_document_reading": "Reading with the document model…",
    "screen_document_progress": (
        "{backend} is reading on {device}… {seconds} seconds elapsed (up to 4 minutes)."
    ),
    "screen_document_timeout": (
        "The document model did not finish within 4 minutes on this device. "
        "Try another model or a faster runtime."
    ),
    "screen_document_no_text": (
        "{backend} ({device}) returned no readable text from the "
        "captured {app_id} window. "
        "Try the screen text reader above to check whether that window has "
        "readable text."
    ),
    "screen_document_result": "{backend} read the active {app_id} window on {device}.",
    "preferences_heading": "Preferences",
    "preferences_caption": "Choose the language of the control center.",
    "interface_language": "Interface language",
    "dashboard_animation": "Animate dashboard particles",
    "dashboard_renderer": "Dashboard renderer",
    "dashboard_renderer_cpu": "CPU (about 30,000 points)",
    "dashboard_renderer_gpu_light": "GPU Light (about 30,000 points)",
    "dashboard_renderer_gpu_medium": "GPU Medium (about 60,000 points)",
    "dashboard_renderer_gpu_heavy": "GPU Heavy (800,000 points)",
    "dashboard_gpu_fallback": "GPU rendering is unavailable; using CPU rendering.",
    "system_language": "System language",
    "power_off_button": "Power off…",
    "restart_button": "Restart…",
    "log_out_button": "Log out…",
    "suspend_button": "Suspend…",
    "cancel_button": "Cancel",
    "continue_button": "Continue",
    "confirm_button": "Confirm",
    "branding_subtitle": "DESKTOP INTELLIGENCE",
    "branding_footer": "KYRIN  /  V1 CONTROL CENTER",
    "start_at_login": "Start KYRIN when I sign in",
    "apply_startup": "Apply startup setting",
    "startup_saved": "Login startup setting saved.",
    "startup_unavailable": "Installed KYRIN launcher is unavailable.",
    "import_language": "Add language pack…",
    "language_help": "Language packs can be added here without changing code.",
    "conversation_memory_heading": "Conversation memory",
    "conversation_memory_caption": (
        "KYRIN keeps a bounded active history of final speech transcripts "
        "on this device. "
        "Audio is not stored. Earlier words never authorize a new action."
    ),
    "conversation_memory_clear": "Clear active conversation memory…",
    "conversation_memory_review": "Review archived speech transcripts…",
    "conversation_memory_review_title": "Archived conversation memory",
    "conversation_memory_archive_count": "Archived transcripts: {count}",
    "conversation_memory_select": "Select a transcript to read it.",
    "conversation_memory_older": "Load older",
    "conversation_memory_restore": "Restore selected transcript…",
    "conversation_memory_close": "Close",
    "conversation_memory_restore_title": "Restore this transcript?",
    "conversation_memory_restore_question": (
        "Make this transcript available to conversation context again? "
        "It will never authorize an action by itself."
    ),
    "conversation_memory_clear_title": "Clear active conversation memory?",
    "conversation_memory_clear_question": (
        "Delete active speech transcripts? Archived history remains preserved. "
        "This cannot be undone."
    ),
    "conversation_memory_cleared": "Active conversation memory cleared.",
    "conversation_memory_unavailable": "Conversation memory could not be cleared.",
    "power_safe_preview": "Test power confirmation safely (no shutdown)…",
    "power_safe_preview_busy": (
        "Power confirmation preview is already active or unavailable."
    ),
    "diagnostics_latency": "Speech onset to action result",
    "diagnostics_final_to_result": "final text to result",
    "language_added": "Language pack added.",
    "ui_saved": "Interface preferences saved.",
    "state_stopped": "Stopped",
    "state_paused": "Microphone is fully off",
    "state_standby": "Standby: say Start listening",
    "state_mic_starting": "Starting microphone; voice commands are not ready yet",
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

_LOCALE = re.compile(r"^[a-z]{2,3}(?:-[A-Z][a-z]{3})?(?:-(?:[A-Z]{2}|[0-9]{3}))?$")


class TranslationError(ValueError):
    """A language pack or UI preferences file is invalid."""


@dataclass(frozen=True, slots=True)
class UiPreferences:
    locale: str = "en"
    dashboard_animation_enabled: bool = True
    dashboard_renderer: str = "cpu"


class UiTranslations:
    """Install complete JSON catalogs into the user's private config folder."""

    def __init__(self, directory: Path, *, system_locale: str | None = None) -> None:
        if not directory.is_absolute():
            raise ValueError("UI config directory must be absolute")
        self.directory = directory
        self.system_locale = system_locale or QLocale.system().bcp47Name()
        self.load_error: TranslationError | None = None
        try:
            preferences = self._load_preferences()
            active_locale = self._resolve_locale(preferences.locale)
            _, strings = self._catalog(active_locale)
        except TranslationError as error:
            # Keep the damaged file untouched. The English UI can still open,
            # explain the problem, and let the user explicitly save a choice.
            self.load_error = error
            self.preferences = UiPreferences()
            self._strings = ENGLISH
            self.active_locale = "en"
        else:
            self.preferences = preferences
            self._strings = strings
            self.active_locale = active_locale

    def _load_preferences(self) -> UiPreferences:
        path = self.directory / "ui.json"
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return UiPreferences()
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise TranslationError("UI preferences could not be read") from exc
        valid_fields = {
            "locale", "dashboard_animation_enabled", "dashboard_renderer"
        }
        if (
            not isinstance(data, dict)
            or "locale" not in data
            or not set(data) <= valid_fields
        ):
            raise TranslationError("UI preferences have invalid fields")
        locale = data["locale"]
        if not isinstance(locale, str) or (
            locale != "system" and not _LOCALE.fullmatch(locale)
        ):
            raise TranslationError("Invalid UI locale")
        animation = data.get("dashboard_animation_enabled", True)
        renderer = data.get("dashboard_renderer", "cpu")
        # Preserve existing preferences when an older 3D selection is loaded.
        if renderer == "gpu3d":
            renderer = "gpu"
        if (
            not isinstance(animation, bool)
            or not isinstance(renderer, str)
            or renderer not in {"cpu", "gpu", "gpu_medium", "gpu_heavy"}
        ):
            raise TranslationError("Invalid dashboard preferences")
        return UiPreferences(locale, animation, renderer)

    def _resolve_locale(self, choice: str) -> str:
        if choice != "system":
            return choice
        normalized = self.system_locale.replace("_", "-")
        if _LOCALE.fullmatch(normalized):
            parts = normalized.split("-")
            candidates = [normalized]
            if len(parts) == 3:
                candidates.extend(("-".join(parts[:2]), f"{parts[0]}-{parts[2]}"))
            candidates.append(parts[0])
            for candidate in dict.fromkeys(candidates):
                try:
                    self._catalog(candidate)
                except TranslationError:
                    continue
                return candidate
        return "en"

    def _catalog(self, locale: str) -> tuple[str, dict[str, str]]:
        if locale == "en":
            return "English", ENGLISH
        if not _LOCALE.fullmatch(locale):
            raise TranslationError("Invalid UI locale")
        path = self.directory / "languages" / f"{locale}.json"
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            if locale == "fa":
                return "فارسی", {**ENGLISH, **PERSIAN}
            raise TranslationError(
                f"Language pack {locale} could not be read"
            ) from None
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise TranslationError(f"Language pack {locale} could not be read") from exc
        self._validate_pack(data, locale)
        return data["name"], {**ENGLISH, **data["strings"]}

    @staticmethod
    def _validate_pack(data: object, locale: str) -> None:
        if (
            not isinstance(data, dict)
            or set(data) != {"locale", "name", "strings"}
            or data["locale"] != locale
            or not isinstance(data["name"], str)
            or not data["name"].strip()
            or not isinstance(data["strings"], dict)
            or not data["strings"]
            or not set(data["strings"]).issubset(ENGLISH)
        ):
            raise TranslationError("Language pack has invalid fields")
        formatter = Formatter()
        for key, value in data["strings"].items():
            if not isinstance(value, str) or not value.strip():
                raise TranslationError("Language pack has an empty translation")
            try:
                expected = {
                    field
                    for _, field, _, _ in formatter.parse(ENGLISH[key])
                    if field is not None
                }
                actual: set[str] = set()
                for _, field, spec, conversion in formatter.parse(value):
                    if field is None:
                        continue
                    if (
                        not field
                        or "." in field
                        or "[" in field
                        or "{" in (spec or "")
                        or "}" in (spec or "")
                        or conversion is not None
                    ):
                        raise TranslationError("Language pack has invalid placeholders")
                    actual.add(field)
            except ValueError as exc:
                raise TranslationError(
                    "Language pack has invalid placeholders"
                ) from exc
            if actual != expected:
                raise TranslationError("Language pack placeholders do not match")

    def text(self, key: str) -> str:
        return self._strings[key]

    def languages(self) -> tuple[tuple[str, str], ...]:
        languages = [
            ("system", self.text("system_language")),
            ("en", "English"),
            ("fa", "فارسی"),
        ]
        for path in sorted((self.directory / "languages").glob("*.json")):
            try:
                name, _ = self._catalog(path.stem)
            except TranslationError:
                continue
            if path.stem == "fa":
                languages[2] = ("fa", name)
            else:
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
        self._validate_pack(data, locale)
        self._atomic_json(self.directory / "languages" / f"{locale}.json", data)
        if locale == self.active_locale:
            self._strings = {**ENGLISH, **data["strings"]}
        return locale

    def save(self, preferences: UiPreferences) -> None:
        if (
            not isinstance(preferences.dashboard_animation_enabled, bool)
            or not isinstance(preferences.dashboard_renderer, str)
            or preferences.dashboard_renderer
            not in {"cpu", "gpu", "gpu_medium", "gpu_heavy"}
        ):
            raise TranslationError("Invalid dashboard preferences")
        active_locale = self._resolve_locale(preferences.locale)
        _, strings = self._catalog(active_locale)
        self._atomic_json(
            self.directory / "ui.json",
            {
                "locale": preferences.locale,
                "dashboard_animation_enabled": preferences.dashboard_animation_enabled,
                "dashboard_renderer": preferences.dashboard_renderer,
            },
        )
        self.preferences = preferences
        self._strings = strings
        self.active_locale = active_locale
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
