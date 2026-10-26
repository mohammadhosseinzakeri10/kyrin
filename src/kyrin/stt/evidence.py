"""Engine observations with named native scores, never intent probabilities."""

from dataclasses import dataclass
from math import isfinite


@dataclass(frozen=True, slots=True)
class SpeechScore:
    name: str
    value: float

    def __post_init__(self) -> None:
        if not self.name.strip() or not isfinite(self.value):
            raise ValueError("speech scores need a name and finite native value")


@dataclass(frozen=True, slots=True)
class SpeechHypothesis:
    text: str
    engine: str
    origin: str = "decoder_alternative"
    scores: tuple[SpeechScore, ...] = ()

    def __post_init__(self) -> None:
        if not self.text.strip() or not self.engine.strip():
            raise ValueError("speech hypotheses require text and engine provenance")
        if self.origin not in {"decoder_alternative", "same_audio_reprocess"}:
            raise ValueError("unknown speech hypothesis origin")


@dataclass(frozen=True, slots=True)
class SpeechEvidence:
    engine: str
    alternatives: tuple[SpeechHypothesis, ...] = ()
    scores: tuple[SpeechScore, ...] = ()

    def __post_init__(self) -> None:
        if not self.engine.strip() or len(self.alternatives) > 4:
            raise ValueError("speech evidence must identify an engine and be bounded")
