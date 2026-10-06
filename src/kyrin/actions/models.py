"""Language-neutral action requests, policy notices, and observed results."""

from dataclasses import dataclass
from enum import StrEnum

from kyrin.commands.models import CommandIntent, ResponseChannel


@dataclass(frozen=True, order=True, slots=True)
class ActionKey:
    """Unique for one command coordinator's lifetime."""

    stream_id: int
    segment_id: int
    step_index: int = 0

    def __post_init__(self) -> None:
        if self.stream_id < 0 or self.segment_id < 0 or self.step_index < 0:
            raise ValueError("action key IDs must not be negative")


@dataclass(frozen=True, slots=True)
class ActionRequest:
    """Authorized intent for an executor; contains no shell command."""

    key: ActionKey
    intent: CommandIntent
    language: str | None = None


class ActionNoticeReason(StrEnum):
    NOT_ALLOWED = "not_allowed"
    CONFIRMATION_REQUIRED = "confirmation_required"
    BUSY = "busy"
    CANCELLED = "cancelled"
    UNSUPPORTED = "unsupported"
    DEPENDENCY_UNVERIFIED = "dependency_unverified"


@dataclass(frozen=True, slots=True)
class ActionNotice:
    """A policy outcome that does not authorize an action."""

    key: ActionKey
    intent: CommandIntent
    reason: ActionNoticeReason
    channel: ResponseChannel = ResponseChannel.TEXT_AND_VOICE
    language: str | None = None


ActionDecision = ActionRequest | ActionNotice


class ActionOutcome(StrEnum):
    """Separate a confirmed action from a launch request or unknown result."""

    CONFIRMED = "confirmed"
    LAUNCH_ACCEPTED = "launch_accepted"
    UNKNOWN = "unknown"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class ActionResult:
    """Report from a future executor, never inferred from spoken text."""

    key: ActionKey
    outcome: ActionOutcome
    observed_active_app: str | None = None
    error_code: str | None = None

    def __post_init__(self) -> None:
        if (
            self.outcome is not ActionOutcome.CONFIRMED
            and self.observed_active_app is not None
        ):
            raise ValueError("only confirmed actions can verify an active app")
        if (
            self.observed_active_app is not None
            and not self.observed_active_app.strip()
        ):
            raise ValueError("observed_active_app must not be empty")
        if self.error_code is not None and not self.error_code.strip():
            raise ValueError("error_code must not be empty")
        if self.outcome in (ActionOutcome.CONFIRMED, ActionOutcome.LAUNCH_ACCEPTED):
            if self.error_code is not None:
                raise ValueError(
                    "confirmed or accepted actions cannot report an error_code"
                )
        elif self.error_code is None:
            raise ValueError("unknown or failed actions require an error_code")


@dataclass(frozen=True, slots=True)
class ActionFeedback:
    """Structured outcome for a future localized text/voice presenter."""

    key: ActionKey
    intent: CommandIntent
    outcome: ActionOutcome
    channel: ResponseChannel
    error_code: str | None = None
    language: str | None = None
    observed_active_app: str | None = None
