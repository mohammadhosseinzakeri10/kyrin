"""Backend-independent OCR input, output, and runtime contracts."""

import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Literal, Protocol

_LANGUAGE_CODE = re.compile(r"[a-z][a-z0-9_]*(?:\+[a-z][a-z0-9_]*)*\Z")


class OcrDevice(StrEnum):
    CPU = "cpu"
    GPU = "gpu"


class OcrDevicePreference(StrEnum):
    AUTO = "auto"
    CPU = "cpu"
    GPU = "gpu"


@dataclass(frozen=True, slots=True)
class OcrCapabilities:
    supported_devices: frozenset[OcrDevice]
    supported_languages: frozenset[str]

    def __post_init__(self) -> None:
        if not self.supported_devices or not self.supported_languages:
            raise ValueError("OCR capabilities require devices and languages")


@dataclass(frozen=True, slots=True)
class OcrOptions:
    language: str
    device: OcrDevicePreference = OcrDevicePreference.AUTO
    layout: Literal["sparse", "block"] = "sparse"

    def __post_init__(self) -> None:
        if (
            len(self.language) > 64
            or len(self.language.split("+")) > 4
            or _LANGUAGE_CODE.fullmatch(self.language) is None
        ):
            raise ValueError("OCR language must be a valid language code")
        if not isinstance(self.device, OcrDevicePreference):
            raise ValueError("OCR device must be auto, cpu, or gpu")
        if self.layout not in {"sparse", "block"}:
            raise ValueError("OCR layout must be sparse or block")


@dataclass(frozen=True, slots=True)
class TextBox:
    left: int
    top: int
    width: int
    height: int

    def __post_init__(self) -> None:
        if self.left < 0 or self.top < 0 or self.width <= 0 or self.height <= 0:
            raise ValueError("OCR box must be a positive image region")


@dataclass(frozen=True, slots=True)
class RecognizedText:
    text: str
    box: TextBox
    confidence: float | None

    def __post_init__(self) -> None:
        if not self.text.strip():
            raise ValueError("recognized text must not be blank")
        if self.confidence is not None and not 0 <= self.confidence <= 1:
            raise ValueError("OCR confidence must be between zero and one")


@dataclass(frozen=True, slots=True)
class OcrResult:
    spans: tuple[RecognizedText, ...]
    language: str
    device: OcrDevice
    engine_id: str


class OcrEngine(Protocol):
    @property
    def capabilities(self) -> OcrCapabilities: ...

    def recognize(self, image: bytes, options: OcrOptions) -> OcrResult:
        """Recognize one image; never execute a desktop action.

        Built-in engines honor the context-local kyrin.operations budget and
        own a killable subprocess. In-process plugins must cooperate with that
        budget; ScreenTextReader retains busy ownership until they really exit.
        """
        ...
