"""Exact spoken controls for the three microphone/listening modes."""

import re
from dataclasses import dataclass
from enum import StrEnum

from kyrin.text_normalization import fold_case


class VoiceMode(StrEnum):
    ACTIVE = "active"
    STANDBY = "standby"
    OFF = "off"


@dataclass(frozen=True, slots=True)
class VoiceModeChanged:
    mode: VoiceMode
    previous: VoiceMode | None = None
    source: str = "voice"
    reason: str = "exact_final_control"
    session_id: str = ""
    generation: int = 0
    revision: int = 0
    segment_id: int | None = None


_START = {"start listening", "شروع به گوش دادن کن"}
_STOP = {"stop listening", "گوش دادن را متوقف کن"}
_OFF = {
    "turn microphone off",
    "turn the microphone off",
    "turn off microphone",
    "turn off the microphone",
    "turn microphone off completely",
    "turn the microphone off completely",
    "turn off microphone completely",
    "turn off the microphone completely",
    "میکروفن را کامل خاموش کن",
}


def control_phrase(text: str, *, active: bool) -> VoiceMode | None:
    """Require a whole phrase; ordinary speech cannot change microphone state."""
    # Quotation is not an instruction. Do not erase quote marks into a control.
    if any(mark in text for mark in ('"', "'", "«", "»", "“", "”", "‘", "’")):
        return None
    normalized = " ".join(re.sub(r"[^\w\u0600-\u06ff]+", " ", fold_case(text)).split())
    if normalized in _OFF:
        return VoiceMode.OFF
    if normalized in _STOP:
        return VoiceMode.STANDBY
    if normalized in _START:
        return VoiceMode.ACTIVE
    return None
