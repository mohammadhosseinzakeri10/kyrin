"""Model and backend capabilities relevant to STT selection."""

from dataclasses import dataclass

from kyrin.stt.device import ComputeDevice


@dataclass(frozen=True, slots=True)
class SpeechToTextCapabilities:
    """Features advertised by the configured, locally installed model.

    supported_devices describes backend support, not hardware availability.
    Unknown languages are represented by None, which never means all languages.
    Language coverage says nothing about transcription accuracy.
    """

    supported_devices: frozenset[ComputeDevice]
    supported_languages: frozenset[str] | None
    supports_partial_updates: bool
    supports_language_detection: bool
    supports_vocabulary_hints: bool = False

    def __post_init__(self) -> None:
        if not self.supported_devices:
            raise ValueError("supported_devices must not be empty")
        if self.supported_languages is not None and not self.supported_languages:
            raise ValueError("supported_languages must not be empty")
