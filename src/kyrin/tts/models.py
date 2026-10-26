"""Portable configuration values shared by TTS engines and the application."""

import re
from dataclasses import dataclass
from pathlib import Path

from kyrin.stt.device import DevicePreference
from kyrin.tts.families import TTS_FAMILY_BY_KEY

_IDENTIFIER = re.compile(r"[a-z][a-z0-9_-]*\Z")


@dataclass(frozen=True, slots=True)
class TtsSelection:
    """A local voice choice; model files are never downloaded by KYRIN."""

    backend: str = "speech-dispatcher"
    model_path: Path | None = None
    voice: str = "default"
    speed: float = 0.75
    device: DevicePreference = DevicePreference.AUTO

    def __post_init__(self) -> None:
        if not isinstance(self.backend, str) or not _IDENTIFIER.fullmatch(self.backend):
            raise ValueError("TTS engine must be a lowercase identifier")
        if not isinstance(self.device, DevicePreference):
            raise ValueError("TTS device must be auto, cpu, or gpu")
        if type(self.speed) not in (int, float) or not 0.5 <= self.speed <= 1.5:
            raise ValueError("TTS speed must be between 0.5 and 1.5")
        if self.backend == "speech-dispatcher":
            if self.model_path is not None or self.voice not in {
                "default",
                "male1",
                "male2",
                "female1",
                "female2",
            }:
                raise ValueError("invalid system voice selection")
            if self.device is DevicePreference.GPU:
                raise ValueError("system voice is CPU-only")
        elif (
            not isinstance(self.model_path, Path)
            or not self.model_path.is_absolute()
            or not self.voice.isdecimal()
            or int(self.voice) > 255
            or (
                self.backend in TTS_FAMILY_BY_KEY
                and int(self.voice) > TTS_FAMILY_BY_KEY[self.backend].max_voice
            )
        ):
            raise ValueError("TTS model needs an absolute folder and voice number")


@dataclass(frozen=True, slots=True)
class TtsLanguageRoute:
    """Use an installed voice for one spoken response language."""

    language: str
    selection: TtsSelection

    def __post_init__(self) -> None:
        if not re.fullmatch(r"[a-z]{2,3}(?:-[A-Z]{2})?", self.language):
            raise ValueError("TTS language must be a code such as fa or en-US")
        if not isinstance(self.selection, TtsSelection):
            raise ValueError("TTS language route needs a voice selection")
