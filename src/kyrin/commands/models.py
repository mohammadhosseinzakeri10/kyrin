"""Small domain types shared by command interpreters and stream consumers."""

from dataclasses import dataclass
from enum import StrEnum

from kyrin.commands.app_names import SpokenAppCandidate


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
class CommandPlan:
    """An ordered, bounded set of steps from one spoken command."""

    steps: tuple[CommandIntent, ...]

    def __post_init__(self) -> None:
        if not 2 <= len(self.steps) <= 3:
            raise ValueError("a command plan requires two or three steps")


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
    candidates: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class PendingAppClarification:
    """A proposed app name awaiting confirmation or a choice."""

    candidates: tuple[SpokenAppCandidate, ...]
    confirmation: bool


class ResponseChannel(StrEnum):
    TEXT_ONLY = "text_only"
    TEXT_AND_VOICE = "text_and_voice"


class ResponseKind(StrEnum):
    CHOOSE_CHAT_APP = "choose_chat_app"
    CHOOSE_APP = "choose_app"
    CONFIRM_APP = "confirm_app"
    REPEAT_COMMAND = "repeat_command"


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
    language: str | None = None
    step_index: int = 0


@dataclass(frozen=True, slots=True)
class CommandPlanResolution:
    """A final ordered plan; the entire utterance has been interpreted."""

    segment_id: int
    plan: CommandPlan
    stream_id: int = 0
    language: str | None = None


@dataclass(frozen=True, slots=True)
class ResponseRequest:
    segment_id: int
    kind: ResponseKind
    channel: ResponseChannel
    stream_id: int = 0
    target: str | None = None
    app_candidates: tuple[str, ...] = ()
    language: str | None = None

    def __post_init__(self) -> None:
        if self.kind is ResponseKind.REPEAT_COMMAND and (
            self.target is not None or self.app_candidates
        ):
            raise ValueError("repeat command must not have chat details")
        if self.kind is ResponseKind.CHOOSE_CHAT_APP and (
            self.target is None or not self.target.strip()
        ):
            raise ValueError("chat clarification requires a target")
        if self.kind is ResponseKind.CONFIRM_APP and (
            self.target is None or not self.target.strip()
        ):
            raise ValueError("app confirmation requires a name")
        if self.kind is ResponseKind.CHOOSE_APP and len(self.app_candidates) < 2:
            raise ValueError("app choice requires at least two candidates")


CommandEvent = (
    CommandCandidateUpdate | CommandResolution | CommandPlanResolution | ResponseRequest
)
