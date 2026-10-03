"""Transcript events shared by streaming and windowed STT backends."""

from dataclasses import dataclass
from enum import StrEnum


class TranscriptStatus(StrEnum):
    """A partial segment can change; a final segment cannot."""

    PARTIAL = "partial"
    FINAL = "final"


@dataclass(frozen=True, slots=True)
class TranscriptUpdate:
    """The current text for one segment in a continuous audio session.

    Updates with the same segment_id replace earlier partial text. A final
    update seals that segment, not the conversation or listening session.
    """

    segment_id: int
    text: str
    status: TranscriptStatus
    language: str | None = None

    def __post_init__(self) -> None:
        if self.segment_id < 0:
            raise ValueError("segment_id must not be negative")
        if self.language is not None and not self.language.strip():
            raise ValueError("language must not be empty")
