"""Engine-neutral meaning proposed from text, before target resolution or permission.

This boundary is deliberately separate from ``CommandIntent``. A proposed
meaning may contain an unresolved name, negation, or several interpretations;
none of those can be sent directly to an action executor.
"""

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from kyrin.commands.models import CommandContext


class RequestedOperation(StrEnum):
    OPEN_APP = "open_app"
    OPEN_CHAT = "open_chat"
    RESTORE_APP = "restore_app"
    MINIMIZE_APP = "minimize_app"
    CLOSE_APP_WINDOW = "close_app_window"
    MAXIMIZE_APP = "maximize_app"
    UNMAXIMIZE_APP = "unmaximize_app"
    FULLSCREEN_APP = "fullscreen_app"
    UNFULLSCREEN_APP = "unfullscreen_app"
    POWER_OFF_SYSTEM = "power_off_system"
    RESTART_SYSTEM = "restart_system"
    LOG_OUT_SYSTEM = "log_out_system"
    SUSPEND_SYSTEM = "suspend_system"


class Polarity(StrEnum):
    AFFIRMATIVE = "affirmative"
    NEGATED = "negated"
    UNCERTAIN = "uncertain"


class UnderstandingStatus(StrEnum):
    READY = "ready"
    NEGATED = "negated"
    AMBIGUOUS = "ambiguous"
    INCOMPLETE = "incomplete"
    NOT_COMMAND = "not_command"
    UNSUPPORTED = "unsupported"


class UncertaintyKind(StrEnum):
    SPEECH = "speech"
    LANGUAGE = "language"
    OPERATION = "operation"
    TARGET = "target"
    NEGATION = "negation"
    CONTEXT = "context"


@dataclass(frozen=True, slots=True)
class UnderstandingInput:
    """Original text, not a translation or a claim about ASR confidence."""

    text: str
    language: str | None = None
    alternatives: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.language is not None and not self.language.strip():
            raise ValueError("language must not be empty")
        if any(not item.strip() for item in self.alternatives):
            raise ValueError("alternative transcripts must contain text")


@dataclass(frozen=True, slots=True)
class MeaningStep:
    """A proposed operation and spoken target, before catalog lookup.

    ``target_phrase`` retains the user's words (for example, a misheard app
    name). ``app_phrase`` is optional context for a chat target. Canonical app
    IDs are assigned later, after checking installed and permitted apps.
    """

    operation: RequestedOperation
    target_phrase: str | None = None
    app_phrase: str | None = None
    polarity: Polarity = Polarity.AFFIRMATIVE

    def __post_init__(self) -> None:
        system_operation = self.operation in {
            RequestedOperation.POWER_OFF_SYSTEM,
            RequestedOperation.RESTART_SYSTEM,
            RequestedOperation.LOG_OUT_SYSTEM,
            RequestedOperation.SUSPEND_SYSTEM,
        }
        if system_operation and (self.target_phrase is not None or self.app_phrase):
            raise ValueError("system operations have no application target")
        if not system_operation and (
            self.target_phrase is None or not self.target_phrase.strip()
        ):
            raise ValueError("application and chat operations require a target")
        if self.app_phrase is not None and (
            self.operation is not RequestedOperation.OPEN_CHAT
            or not self.app_phrase.strip()
        ):
            raise ValueError("app_phrase is only valid for a chat operation")


@dataclass(frozen=True, slots=True)
class ProposedMeaning:
    """Ordered semantic steps; a later planner decides its supported limit."""

    steps: tuple[MeaningStep, ...]

    def __post_init__(self) -> None:
        if not self.steps:
            raise ValueError("a proposed meaning requires at least one step")


@dataclass(frozen=True, slots=True)
class UnderstandingResult:
    """Interpretation candidates, never authorization to perform an action.

    READY requires one affirmative, unambiguous interpretation. NEGATED holds
    one clear interpretation containing a negated step but authorizes nothing.
    AMBIGUOUS may carry competing candidates. The remaining statuses carry no
    candidate.
    Raw input lives in UnderstandingInput; adapters must not replace it with
    translated text without retaining its original provenance.
    """

    status: UnderstandingStatus
    candidates: tuple[ProposedMeaning, ...] = ()
    uncertainties: frozenset[UncertaintyKind] = frozenset()

    def __post_init__(self) -> None:
        if self.status is UnderstandingStatus.READY:
            if len(self.candidates) != 1 or self.uncertainties:
                raise ValueError("ready requires one unambiguous candidate")
            if any(
                step.polarity is not Polarity.AFFIRMATIVE
                for step in self.candidates[0].steps
            ):
                raise ValueError("negated or uncertain steps cannot be ready")
        elif self.status is UnderstandingStatus.NEGATED:
            if len(self.candidates) != 1 or self.uncertainties:
                raise ValueError("negated requires one unambiguous candidate")
            polarities = {step.polarity for step in self.candidates[0].steps}
            if Polarity.NEGATED not in polarities or Polarity.UNCERTAIN in polarities:
                raise ValueError("negated result requires a known negative step")
        elif self.status is UnderstandingStatus.AMBIGUOUS:
            if not self.uncertainties:
                raise ValueError("ambiguous results require an uncertainty reason")
        elif self.candidates:
            raise ValueError("non-command results cannot propose actions")


class CommandUnderstandingEngine(Protocol):
    """A local multilingual model or translation-backed implementation."""

    def understand(
        self, utterance: UnderstandingInput, *, context: CommandContext
    ) -> UnderstandingResult: ...
