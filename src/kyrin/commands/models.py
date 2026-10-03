"""Small domain types shared by command interpreters and stream consumers."""

from dataclasses import dataclass
from enum import StrEnum


class CommandKind(StrEnum):
    OPEN_APP = "open_app"
    OPEN_CHAT = "open_chat"


@dataclass(frozen=True, slots=True)
class CommandIntent:
    kind: CommandKind
    target: str
    app: str | None = None

    def __post_init__(self) -> None:
        if not self.target.strip():
            raise ValueError("command target must not be empty")
        if self.kind is CommandKind.OPEN_APP and self.app is not None:
            raise ValueError("open_app must not have a separate app")
        if self.kind is CommandKind.OPEN_CHAT and (
            self.app is None or not self.app.strip()
        ):
            raise ValueError("open_chat requires a verified or explicit app")


@dataclass(frozen=True, slots=True)
class VerifiedContext:
    """Facts supplied by the application after successful actions only."""

    active_app: str | None = None


@dataclass(frozen=True, slots=True)
class CommandContext:
    """Dialogue history and a fresh foreground observation are distinct facts."""

    last_referenced_app: str | None = None
    observed_active_app: str | None = None


@dataclass(frozen=True, slots=True)
class PendingClarification:
    """A chat target waiting for the application name."""

    target: str
    question: str


class ResponseChannel(StrEnum):
    TEXT_ONLY = "text_only"
    TEXT_AND_VOICE = "text_and_voice"


@dataclass(frozen=True, slots=True)
class CommandCandidateUpdate:
    """A replaceable partial-text candidate; None retracts a prior candidate."""

    segment_id: int
    intent: CommandIntent | None
    stream_id: int = 0


@dataclass(frozen=True, slots=True)
class CommandResolution:
    """Final decision for a segment, replacing any candidate with this ID."""

    segment_id: int
    intent: CommandIntent | None
    stream_id: int = 0


@dataclass(frozen=True, slots=True)
class ResponseRequest:
    segment_id: int
    text: str
    channel: ResponseChannel
    stream_id: int = 0


CommandEvent = CommandCandidateUpdate | CommandResolution | ResponseRequest
