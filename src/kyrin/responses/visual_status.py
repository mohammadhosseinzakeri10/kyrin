"""Small, UI-independent visual states derived from structured runtime events."""

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from threading import Lock

from kyrin.actions.models import (
    ActionDecision,
    ActionFeedback,
    ActionNotice,
    ActionOutcome,
    ActionRequest,
)
from kyrin.audio.activity.speech_activity_monitor import (
    SpeechActivityFrame,
    SpeechTransition,
)
from kyrin.audio.live_speech_pipeline import LiveSpeechEvent
from kyrin.commands.models import (
    CommandEvent,
    CommandKind,
    CommandResolution,
    ResponseKind,
    ResponseRequest,
)
from kyrin.responses.presenter import ResponsePresenter
from kyrin.stt.transcript import TranscriptUpdate


class VisualStatus(StrEnum):
    READY = "ready"
    CONVERSATION = "conversation"
    LISTENING = "listening"
    PROCESSING = "processing"
    QUESTION = "question"
    EXECUTING = "executing"
    CONFIRMED = "confirmed"
    UNVERIFIED = "unverified"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class VisualPresentation:
    """A short, localized description of the state shown by any visual adapter."""

    status: VisualStatus
    caption: str


_CAPTIONS = {
    "en": {
        VisualStatus.READY: "Ready to listen…",
        VisualStatus.CONVERSATION: "Responding…",
        VisualStatus.LISTENING: "Listening…",
        VisualStatus.PROCESSING: "Understanding speech…",
        VisualStatus.QUESTION: "Please clarify…",
        VisualStatus.EXECUTING: "Working…",
        VisualStatus.CONFIRMED: "Done.",
        VisualStatus.UNVERIFIED: "Request sent; checking…",
        VisualStatus.FAILED: "Could not complete that.",
    },
    "fa": {
        VisualStatus.READY: "آمادهٔ شنیدن…",
        VisualStatus.CONVERSATION: "در حال پاسخ‌دادن…",
        VisualStatus.LISTENING: "در حال گوش‌دادن…",
        VisualStatus.PROCESSING: "در حال بررسی گفتار…",
        VisualStatus.QUESTION: "لطفاً توضیح دهید…",
        VisualStatus.EXECUTING: "در حال انجام کار…",
        VisualStatus.CONFIRMED: "انجام شد.",
        VisualStatus.UNVERIFIED: "درخواست ارسال شد؛ در حال بررسی…",
        VisualStatus.FAILED: "نتوانستم کار را انجام دهم.",
    },
}


def _caption_language(language: str | None) -> str:
    primary = (language or "en").strip().replace("_", "-").split("-", 1)[0].lower()
    return primary if primary in _CAPTIONS else "en"


class VisualStatusController:
    """Publish state changes without confusing execution with completion.

    The action worker and audio consumer may call this concurrently. While an
    action is executing, newer transcripts cannot replace its running state.
    """

    def __init__(
        self,
        publish: Callable[[VisualPresentation], None],
        *,
        language: str = "en",
    ) -> None:
        self._publish = publish
        self._language = _caption_language(language)
        self._presenter = ResponsePresenter(language)
        self._lock = Lock()
        self._presentation: VisualPresentation | None = None
        self._executing = False
        self._set(VisualStatus.READY)

    def _set(
        self,
        status: VisualStatus,
        *,
        caption: str | None = None,
        language: str | None = None,
        executing: bool | None = None,
        unless_executing: bool = False,
    ) -> None:
        with self._lock:
            if unless_executing and self._executing:
                return
            if language is not None:
                self._language = _caption_language(language)
            if executing is not None:
                self._executing = executing
            presentation = VisualPresentation(
                status,
                caption or _CAPTIONS[self._language][status],
            )
            if self._presentation == presentation:
                return
            self._presentation = presentation
            self._publish(presentation)

    def on_live_event(self, event: LiveSpeechEvent) -> None:
        if isinstance(event, TranscriptUpdate):
            self._set(
                VisualStatus.PROCESSING,
                language=event.language,
                unless_executing=True,
            )
        elif (
            isinstance(event, SpeechActivityFrame)
            and event.transition is SpeechTransition.STARTED
        ):
            self._set(VisualStatus.LISTENING, unless_executing=True)

    def on_command_event(self, event: CommandEvent) -> None:
        if (
            isinstance(event, ResponseRequest)
            and event.kind is ResponseKind.CONVERSATION
        ):
            self._set(
                VisualStatus.CONVERSATION,
                caption=self._presenter.present(event).text,
                language=event.language,
                unless_executing=True,
            )
        elif (
            isinstance(event, ResponseRequest)
            and event.kind is ResponseKind.READY_FOR_COMMAND
        ):
            self._set(
                VisualStatus.READY,
                caption=self._presenter.present(event).text,
                language=event.language,
                unless_executing=True,
            )
        elif isinstance(event, ResponseRequest):
            self._set(
                VisualStatus.QUESTION,
                caption=self._presenter.present(event).text,
                language=event.language,
                unless_executing=True,
            )
        elif isinstance(event, CommandResolution) and event.intent is None:
            # A final non-command or negation ends processing. A following
            # clarification request, when present, replaces READY with QUESTION.
            self._set(
                VisualStatus.READY,
                language=event.language,
                unless_executing=True,
            )

    def on_action_start(self, request: ActionRequest) -> None:
        language = _caption_language(request.language or self._language)
        if request.intent.kind is CommandKind.OPEN_APP:
            caption = (
                f"در حال بازکردن {request.intent.target}…"
                if language == "fa"
                else f"Opening {request.intent.target}…"
            )
        elif request.intent.kind is CommandKind.OPEN_CHAT:
            caption = (
                f"در حال بازکردن چت {request.intent.target}…"
                if language == "fa"
                else f"Opening {request.intent.target}'s chat…"
            )
        else:
            caption = (
                f"در حال انجام فرمان روی {request.intent.target}…"
                if language == "fa"
                else f"Working with {request.intent.target}…"
            )
        self._set(
            VisualStatus.EXECUTING,
            caption=caption,
            language=language,
            executing=True,
        )

    def on_action_error(self) -> None:
        """An executor raised before it could return structured feedback."""
        self._set(VisualStatus.FAILED, executing=False)

    def on_action_output(self, output: ActionDecision | ActionFeedback) -> None:
        if isinstance(output, ActionRequest):
            # An authorized dry-run decision never starts an OS action.
            self._set(VisualStatus.READY)
            return
        if isinstance(output, ActionNotice):
            # A BUSY notice can arrive while the worker is running another
            # action. Its text is still shown, but it must not stop the run icon.
            self._set(
                VisualStatus.FAILED,
                caption=self._presenter.present(output).text,
                language=output.language,
                unless_executing=True,
            )
            return
        if (
            output.intent.kind in (
                CommandKind.SHOW_APP_WINDOWS, CommandKind.SHOW_ALL_WINDOWS,
            )
            and output.outcome is ActionOutcome.LAUNCH_ACCEPTED
        ):
            self._set(
                VisualStatus.QUESTION,
                caption=(
                    "شمارهٔ پنجره را بگویید یا روی آن کلیک کنید."
                    if _caption_language(output.language) == "fa"
                    else "Say a window number or click its preview."
                ),
                language=output.language,
                executing=False,
            )
            return
        status = {
            ActionOutcome.CONFIRMED: VisualStatus.CONFIRMED,
            ActionOutcome.LAUNCH_ACCEPTED: VisualStatus.UNVERIFIED,
            ActionOutcome.UNKNOWN: VisualStatus.UNVERIFIED,
            ActionOutcome.FAILED: VisualStatus.FAILED,
        }[output.outcome]
        self._set(
            status,
            caption=self._presenter.present(output).text,
            language=output.language,
            executing=False,
        )
