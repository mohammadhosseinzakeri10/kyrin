"""Trusted control capabilities and consent; no model output grants authority."""

import re
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Literal

from kyrin.actions.models import ActionKey
from kyrin.desktop.accessibility_target import AccessibilityTarget
from kyrin.desktop.window_observation import WindowObservation


class ControlCapability(StrEnum):
    NAVIGATE = "navigate"
    ACTIVATE = "activate"
    SET_STATE = "set_state"
    CLOSE_WINDOW = "close_window"


class ControlConsequence(StrEnum):
    NAVIGATION = "navigation"
    UNKNOWN = "unknown"
    UNSUPPORTED = "unsupported_consequence"


# Reviewed aliases identify navigation only, never authorize a toggle or a
# consequential action. Unknown labels need independently bound evidence and consent.
_NAVIGATION = {
    "settings": ("settings", "تنظیمات", "einstellungen", "paramètres", "ajustes"),
    "search": ("search", "جست‌وجو", "جستجو", "suchen", "rechercher", "buscar"),
    "help": ("help", "راهنما", "hilfe", "aide", "ayuda"),
    "preferences": ("preferences", "ترجیحات", "préférences", "preferencias"),
    "about": ("about", "درباره", "über", "à propos", "acerca de"),
    "advanced": ("advanced", "پیشرفته", "erweitert", "avancé", "avanzado"),
}
_CONSEQUENCES = re.compile(
    r"\b(?:delete|remove|clear|erase|format|reset|send|submit|share|post|publish|"
    r"upload|buy|purchase|pay|checkout|log out|logout|sign out|signout|quit|exit|"
    r"close)\b|(?:حذف|پاک|فرمت|بازنشانی|ارسال|انتشار|خرید|پرداخت|خروج|بستن)"
)


def normalize_label(label: str) -> str:
    text = unicodedata.normalize("NFKC", label).casefold()
    text = text.replace("ي", "ی").replace("ك", "ک")
    return " ".join(
        "".join(
            " " if unicodedata.category(char).startswith(("P", "S")) else char
            for char in text
        ).split()
    )


def control_policy(
    label: str,
    state: bool | None,
) -> tuple[ControlCapability, ControlConsequence]:
    normalized = normalize_label(label)
    capability = (
        ControlCapability.ACTIVATE if state is None else ControlCapability.SET_STATE
    )
    if _CONSEQUENCES.search(normalized):
        # Generic clicking is not a Send/Delete/Pay capability. Separate tools
        # with explicit permissions and consequence contracts are required.
        return capability, ControlConsequence.UNSUPPORTED
    if state is None and any(normalized in aliases for aliases in _NAVIGATION.values()):
        return ControlCapability.NAVIGATE, ControlConsequence.NAVIGATION
    return capability, ControlConsequence.UNKNOWN


@dataclass(frozen=True, slots=True)
class ControlEvidence:
    label: str
    source: Literal["accessibility", "ocr", "window"]
    role: str | None
    checked: bool | None
    anchor: tuple[int, int] | None
    accessibility: AccessibilityTarget | None = None
    # OCR: label box, image size and capture/frame rectangles; no refreshed ID/age.
    bounds: tuple[int, ...] = ()


@dataclass(frozen=True, slots=True)
class ControlConfirmation:
    key: ActionKey
    capability: ControlCapability
    target: ControlEvidence
    window: WindowObservation
    desired_state: bool | None
    language: str | None = None


ControlConfirmer = Callable[[ControlConfirmation], bool]


@dataclass(slots=True)
class ControlApproval:
    """One request binding, expiring at the original observation deadline.

    Persistent consent comes from PermissionPolicy in the application path;
    legacy callers may obtain consent from a button. Neither renews evidence.

    Even a failed consumption burns the decision. It is local to the executor,
    never a field accepted from an interpreter or a model.
    """

    confirmation: ControlConfirmation
    _used: bool = False

    def consume(self, fresh: ControlConfirmation, now: float) -> bool:
        used, self._used = self._used, True
        return (
            not used
            and fresh == self.confirmation
            and self.confirmation.window.current(fresh.window.window_token, now)
        )
