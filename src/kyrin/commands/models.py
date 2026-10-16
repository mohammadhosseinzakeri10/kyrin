"""Small domain types shared by command interpreters and stream consumers."""

from dataclasses import dataclass
from enum import StrEnum

from kyrin.commands.app_names import SpokenAppCandidate


class CommandKind(StrEnum):
    OPEN_APP = "open_app"
    OPEN_CHAT = "open_chat"
    SCROLL_UP = "scroll_up"
    SCROLL_DOWN = "scroll_down"
    RESTORE_APP = "restore_app"
    MINIMIZE_APP = "minimize_app"
    CLOSE_APP_WINDOW = "close_app_window"
    MAXIMIZE_APP = "maximize_app"
    UNMAXIMIZE_APP = "unmaximize_app"
    FULLSCREEN_APP = "fullscreen_app"
    UNFULLSCREEN_APP = "unfullscreen_app"
    NEW_APP_WINDOW = "new_app_window"
    NEW_APP_TAB = "new_app_tab"
    APP_PREFERENCES = "app_preferences"
    SHOW_ALL_WINDOWS = "show_all_windows"
    SHOW_APP_WINDOWS = "show_app_windows"
    SELECT_APP_WINDOW = "select_app_window"
    CLOSE_SHOWN_WINDOW = "close_shown_window"
    HIDE_APP_WINDOWS = "hide_app_windows"
    SELECT_OPEN_APP_WINDOW = "select_open_app_window"


@dataclass(frozen=True, slots=True)
class CommandIntent:
    kind: CommandKind
    target: str
    app: str | None = None
    window_index: int | None = None
    scroll_steps: int | None = None

    def __post_init__(self) -> None:
        if not self.target.strip():
            raise ValueError("command target must not be empty")
        if self.kind is not CommandKind.OPEN_CHAT and self.app is not None:
            raise ValueError("app window commands must not have a separate app")
        if self.kind is CommandKind.OPEN_CHAT and (
            self.app is None or not self.app.strip()
        ):
            raise ValueError("open_chat requires a verified or explicit app")
        if self.kind in (CommandKind.SELECT_APP_WINDOW, CommandKind.CLOSE_SHOWN_WINDOW):
            if type(self.window_index) is not int or self.window_index < 1:
                raise ValueError(
                    "numbered window action requires a positive window number"
                )
        elif self.window_index is not None:
            raise ValueError("only numbered window actions may carry a window number")
        if self.kind in (CommandKind.SCROLL_UP, CommandKind.SCROLL_DOWN):
            if self.scroll_steps is not None and (
                type(self.scroll_steps) is not int
                or not 1 <= self.scroll_steps <= 4
            ):
                raise ValueError("scroll steps must be an integer from 1 to 4")
        elif self.scroll_steps is not None:
            raise ValueError("only scroll actions may carry scroll steps")


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
    is_final_transcript: bool = True
    recent_utterances: tuple[str, ...] = ()
    recent_scroll_kind: CommandKind | None = None
    recent_scroll_steps: int | None = None


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
    operation: CommandKind | None = CommandKind.OPEN_APP


@dataclass(frozen=True, slots=True)
class PendingOperationClarification:
    """An app was named, but the requested operation is still unknown."""

    app_candidate: SpokenAppCandidate
    options: tuple[CommandKind, ...]


@dataclass(frozen=True, slots=True)
class PendingWindowSelection:
    """A numbered picker already requested for one registered application."""

    app_candidate: SpokenAppCandidate
    count: int
    all_apps: bool = False


@dataclass(frozen=True, slots=True)
class PendingActionConfirmation:
    """A potentially disruptive menu choice awaits a distinct yes/no answer."""

    app_candidate: SpokenAppCandidate
    operation: CommandKind


@dataclass(frozen=True, slots=True)
class PendingNumberedCloseConfirmation:
    """A selected picker tile awaits a separate yes/no before closing."""

    app_candidate: SpokenAppCandidate
    window_index: int
    count: int
    all_apps: bool = False


@dataclass(frozen=True, slots=True)
class PendingIntentClarification:
    """An exact app name also reads as a chat command."""

    app_candidate: SpokenAppCandidate
    chat_target: str
    chat_app: str | None = None


PendingCommandClarification = (
    PendingClarification
    | PendingAppClarification
    | PendingIntentClarification
    | PendingOperationClarification
    | PendingActionConfirmation
    | PendingNumberedCloseConfirmation
    | PendingWindowSelection
)


class ResponseChannel(StrEnum):
    TEXT_ONLY = "text_only"
    TEXT_AND_VOICE = "text_and_voice"


class ResponseKind(StrEnum):
    READY_FOR_COMMAND = "ready_for_command"
    CHOOSE_CHAT_APP = "choose_chat_app"
    CHOOSE_APP = "choose_app"
    CONFIRM_APP = "confirm_app"
    CHOOSE_APP_OR_CHAT = "choose_app_or_chat"
    CHOOSE_OPERATION = "choose_operation"
    CHOOSE_WINDOW = "choose_window"
    CONFIRM_ACTION = "confirm_action"
    CONFIRM_NUMBERED_CLOSE = "confirm_numbered_close"
    REPEAT_COMMAND = "repeat_command"
    CONVERSATION = "conversation"


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
    message: str | None = None
    operation_candidates: tuple[CommandKind, ...] = ()
    window_count: int = 0
    window_index: int = 0

    def __post_init__(self) -> None:
        if self.kind is ResponseKind.CONVERSATION:
            if (
                self.message is None
                or not self.message.strip()
                or len(self.message) > 300
                or self.target is not None
                or self.app_candidates
            ):
                raise ValueError("conversation requires only a short message")
        elif self.message is not None:
            raise ValueError("only conversation may carry a message")
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
        if self.kind is ResponseKind.CHOOSE_APP_OR_CHAT and (
            self.target is None or not self.target.strip()
        ):
            raise ValueError("app-or-chat clarification requires an app name")
        if self.kind is ResponseKind.CHOOSE_APP and len(self.app_candidates) < 2:
            raise ValueError("app choice requires at least two candidates")
        if self.kind is ResponseKind.CHOOSE_OPERATION and (
            self.target is None or not self.operation_candidates
        ):
            raise ValueError("operation choice requires a target and options")
        if self.kind is ResponseKind.CONFIRM_ACTION and (
            self.target is None or len(self.operation_candidates) != 1
        ):
            raise ValueError("action confirmation requires one operation")
        if self.kind is ResponseKind.CONFIRM_NUMBERED_CLOSE and (
            self.window_index < 1 or self.target is None
        ):
            raise ValueError("numbered close confirmation requires a window number")


CommandEvent = (
    CommandCandidateUpdate | CommandResolution | CommandPlanResolution | ResponseRequest
)
