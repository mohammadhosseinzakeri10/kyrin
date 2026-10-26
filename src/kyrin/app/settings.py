"""Typed, platform-neutral preferences for the future KYRIN application."""

import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from kyrin.memory.history import HistoryRetention
from kyrin.stt.device import DevicePreference
from kyrin.tts.models import (
    TtsLanguageRoute as TtsLanguageRoute,
)
from kyrin.tts.models import (
    TtsSelection as TtsSelection,
)
from kyrin.vision.ocr.contracts import OcrDevicePreference

_IDENTIFIER = re.compile(r"[a-z][a-z0-9_-]*\Z")


def _spoken_alias_key(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    normalized = normalized.replace("ي", "ی").replace("ك", "ک")
    return " ".join(re.findall(r"[^\W_]+", normalized, flags=re.UNICODE))


@dataclass(frozen=True, slots=True)
class SttSelection:
    """An installed model request; availability is checked when it is opened."""

    backend: str
    model_path: Path
    language: str
    device: DevicePreference = DevicePreference.AUTO

    def __post_init__(self) -> None:
        if not isinstance(self.backend, str) or not _IDENTIFIER.fullmatch(self.backend):
            raise ValueError("STT backend must be a lowercase identifier")
        if not isinstance(self.model_path, Path) or not self.model_path.is_absolute():
            raise ValueError("STT model path must be absolute")
        if (
            not isinstance(self.language, str)
            or not self.language
            or any(character.isspace() for character in self.language)
        ):
            raise ValueError("STT language must be a nonempty language code")
        if not isinstance(self.device, DevicePreference):
            raise ValueError("STT device must be auto, cpu, or gpu")


@dataclass(frozen=True, slots=True)
class CommandModelSelection:
    """One local command model; absence keeps the bounded rule interpreter."""

    backend: str
    model: str
    store_path: Path
    device: DevicePreference = DevicePreference.AUTO

    def __post_init__(self) -> None:
        if self.backend != "ollama":
            raise ValueError("command model backend is not installed")
        if not self.model or any(char.isspace() for char in self.model):
            raise ValueError("command model name must be nonempty")
        if not self.store_path.is_absolute():
            raise ValueError("command model store path must be absolute")
        if not isinstance(self.device, DevicePreference):
            raise ValueError("command model device must be auto, cpu, or gpu")


@dataclass(frozen=True, slots=True)
class OcrSelection:
    """A user-selected local OCR package, resolved by an installed adapter."""

    backend: str
    model_path: Path

    def __post_init__(self) -> None:
        if not isinstance(self.backend, str) or not _IDENTIFIER.fullmatch(self.backend):
            raise ValueError("OCR backend must be a lowercase identifier")
        if not isinstance(self.model_path, Path) or not self.model_path.is_absolute():
            raise ValueError("OCR model path must be absolute")


@dataclass(frozen=True, slots=True)
class DocumentOcrSelection:
    """Saved text-only document model and requested compute device."""

    backend: str
    device: OcrDevicePreference = OcrDevicePreference.AUTO

    def __post_init__(self) -> None:
        if self.backend not in {"surya", "glm", "dots"}:
            raise ValueError("document OCR backend is not installed")
        if not isinstance(self.device, OcrDevicePreference):
            raise ValueError("document OCR device must be auto, cpu, or gpu")


@dataclass(frozen=True, slots=True)
class AllowedApp:
    """An explicit Ubuntu desktop-entry binding, not arbitrary shell text."""

    app_id: str
    desktop_id: str

    def __post_init__(self) -> None:
        if not isinstance(self.app_id, str) or not _IDENTIFIER.fullmatch(self.app_id):
            raise ValueError("allowed app ID must be a lowercase identifier")
        if (
            not isinstance(self.desktop_id, str)
            or len(self.desktop_id) <= len(".desktop")
            or not self.desktop_id.endswith(".desktop")
            or "/" in self.desktop_id
            or "\\" in self.desktop_id
        ):
            raise ValueError("allowed app desktop ID must name a .desktop entry")


@dataclass(frozen=True, slots=True)
class AppSpokenAliases:
    """User spellings for one registered app, independent of action permission."""

    platform_id: str
    aliases: tuple[str, ...]

    def __post_init__(self) -> None:
        if (
            not isinstance(self.platform_id, str)
            or not 1 <= len(self.platform_id.strip()) <= 1024
            or any(ord(char) < 32 for char in self.platform_id)
        ):
            raise ValueError("spoken app aliases require a registered app ID")
        if (
            not isinstance(self.aliases, tuple)
            or not 1 <= len(self.aliases) <= 12
            or any(
                not isinstance(alias, str)
                or not 1 <= len(alias.strip()) <= 64
                or any(ord(char) < 32 for char in alias)
                or not _spoken_alias_key(alias)
                for alias in self.aliases
            )
            or len({_spoken_alias_key(alias) for alias in self.aliases})
            != len(self.aliases)
        ):
            raise ValueError("spoken app aliases must be unique short phrases")


@dataclass(frozen=True, slots=True)
class AppSettings:
    """Saved intent, distinct from the actual running/listening state.

    A fresh installation has no selected STT model and allows no desktop
    action. The future application must show setup instead of opening a mic
    until a usable model is selected.
    """

    listening_enabled: bool = True
    start_at_login: bool = True
    microphone_device_key: str | None = None
    stt: SttSelection | None = None
    command_model: CommandModelSelection | None = None
    ocr: OcrSelection | None = None
    document_ocr: DocumentOcrSelection | None = None
    tts: TtsSelection = TtsSelection()
    tts_languages: tuple[TtsLanguageRoute, ...] = ()
    tts_enabled: bool = True
    action_execution_enabled: bool = False
    trust_all_capabilities: bool = False
    capability_grants: tuple[str, ...] = ()
    system_power_enabled: bool = False
    allowed_apps: tuple[AllowedApp, ...] = ()
    allowed_chat_apps: tuple[str, ...] = ()
    remember_telegram_pointer: bool = False
    allow_desktop_scroll: bool = False
    allow_desktop_control: bool = False
    allowed_window_apps: tuple[str, ...] = ()
    allowed_close_apps: tuple[str, ...] = ()
    wake_aliases: tuple[str, ...] = ()
    app_spoken_aliases: tuple[AppSpokenAliases, ...] = ()
    history_enabled: bool = False
    history_retention: HistoryRetention = HistoryRetention()

    def __post_init__(self) -> None:
        if type(self.history_enabled) is not bool:
            raise ValueError("history_enabled must be a boolean")
        if not isinstance(self.history_retention, HistoryRetention):
            raise ValueError("history_retention must be a HistoryRetention policy")
        if type(self.listening_enabled) is not bool:
            raise ValueError("listening_enabled must be a boolean")
        if type(self.start_at_login) is not bool:
            raise ValueError("start_at_login must be a boolean")
        if self.microphone_device_key is not None and (
            not isinstance(self.microphone_device_key, str)
            or not self.microphone_device_key.strip()
        ):
            raise ValueError("microphone_device_key must be nonempty or null")
        if self.stt is not None and not isinstance(self.stt, SttSelection):
            raise ValueError("stt must be a model selection or null")
        if self.command_model is not None and not isinstance(
            self.command_model, CommandModelSelection
        ):
            raise ValueError("command_model must be a model selection or null")
        if self.ocr is not None and not isinstance(self.ocr, OcrSelection):
            raise ValueError("ocr must be a model selection or null")
        if self.document_ocr is not None and not isinstance(
            self.document_ocr, DocumentOcrSelection
        ):
            raise ValueError("document_ocr must be a document model selection or null")
        if not isinstance(self.tts, TtsSelection):
            raise ValueError("tts must be a voice selection")
        if type(self.tts_enabled) is not bool:
            raise ValueError("tts_enabled must be a boolean")
        if (
            not isinstance(self.tts_languages, tuple)
            or not all(
                isinstance(route, TtsLanguageRoute) for route in self.tts_languages
            )
            or len({route.language.casefold() for route in self.tts_languages})
            != len(self.tts_languages)
        ):
            raise ValueError("TTS language routes must have unique languages")
        if type(self.action_execution_enabled) is not bool:
            raise ValueError("action_execution_enabled must be a boolean")
        if type(self.trust_all_capabilities) is not bool:
            raise ValueError("trust_all_capabilities must be a boolean")
        if (
            not isinstance(self.capability_grants, tuple)
            or any(
                not isinstance(item, str) or not _IDENTIFIER.fullmatch(item)
                for item in self.capability_grants
            )
            or len(set(self.capability_grants)) != len(self.capability_grants)
        ):
            raise ValueError("capability grants must be unique identifiers")
        if type(self.system_power_enabled) is not bool:
            raise ValueError("system_power_enabled must be a boolean")
        if not isinstance(self.allowed_apps, tuple) or not all(
            isinstance(binding, AllowedApp) for binding in self.allowed_apps
        ):
            raise ValueError("allowed_apps must contain desktop bindings")
        app_ids = [binding.app_id for binding in self.allowed_apps]
        desktop_ids = [binding.desktop_id for binding in self.allowed_apps]
        if len(app_ids) != len(set(app_ids)) or len(desktop_ids) != len(
            set(desktop_ids)
        ):
            raise ValueError("allowed_apps contains duplicate bindings")
        if (
            not isinstance(self.allowed_chat_apps, tuple)
            or any(
                not isinstance(app_id, str) or not _IDENTIFIER.fullmatch(app_id)
                for app_id in self.allowed_chat_apps
            )
            or len(self.allowed_chat_apps) != len(set(self.allowed_chat_apps))
            or not set(self.allowed_chat_apps).issubset(app_ids)
        ):
            raise ValueError("chat permission requires a unique allowed app")
        if type(self.remember_telegram_pointer) is not bool:
            raise ValueError("remember_telegram_pointer must be a boolean")
        if self.remember_telegram_pointer and "telegram" not in self.allowed_chat_apps:
            raise ValueError("remembered Telegram pointer requires chat permission")
        if type(self.allow_desktop_scroll) is not bool:
            raise ValueError("allow_desktop_scroll must be a boolean")
        if type(self.allow_desktop_control) is not bool:
            raise ValueError("allow_desktop_control must be a boolean")
        for label, identifiers in (
            ("window", self.allowed_window_apps),
            ("close", self.allowed_close_apps),
        ):
            if (
                not isinstance(identifiers, tuple)
                or any(
                    not isinstance(app_id, str) or not _IDENTIFIER.fullmatch(app_id)
                    for app_id in identifiers
                )
                or len(identifiers) != len(set(identifiers))
                or not set(identifiers).issubset(app_ids)
            ):
                raise ValueError(f"{label} permission requires unique allowed apps")
        if (
            not isinstance(self.wake_aliases, tuple)
            or len(self.wake_aliases) > 12
            or any(
                not isinstance(alias, str)
                or not 2 <= len(alias.strip()) <= 40
                or "," in alias
                for alias in self.wake_aliases
            )
            or len({alias.casefold().strip() for alias in self.wake_aliases})
            != len(self.wake_aliases)
        ):
            raise ValueError("wake aliases must be unique short phrases")
        if (
            not isinstance(self.app_spoken_aliases, tuple)
            or len(self.app_spoken_aliases) > 256
            or any(
                not isinstance(item, AppSpokenAliases)
                for item in self.app_spoken_aliases
            )
            or len({item.platform_id for item in self.app_spoken_aliases})
            != len(self.app_spoken_aliases)
            or len(
                {
                    _spoken_alias_key(alias)
                    for item in self.app_spoken_aliases
                    for alias in item.aliases
                }
            )
            != sum(len(item.aliases) for item in self.app_spoken_aliases)
        ):
            raise ValueError("spoken app aliases require unique registered IDs")
