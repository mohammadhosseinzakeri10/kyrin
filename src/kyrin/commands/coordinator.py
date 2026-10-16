"""Turn revisable transcript updates into safe, observable command decisions."""

from collections.abc import Callable, Sequence
from time import monotonic

from kyrin.commands.fragments import CommandFragmentBuffer
from kyrin.commands.interpreter import (
    CommandInterpreter,
    ConversationalReply,
    DeclinedClarification,
    IncompleteCommand,
    NeedsClarification,
    ReadyCommand,
    ReadyPlan,
    UnrecognizedCommand,
    WakeOnly,
)
from kyrin.commands.models import (
    CommandCandidateUpdate,
    CommandContext,
    CommandEvent,
    CommandIntent,
    CommandKind,
    CommandPlanResolution,
    CommandResolution,
    PendingActionConfirmation,
    PendingAppClarification,
    PendingClarification,
    PendingCommandClarification,
    PendingIntentClarification,
    PendingNumberedCloseConfirmation,
    PendingOperationClarification,
    PendingWindowSelection,
    ResponseChannel,
    ResponseKind,
    ResponseRequest,
)
from kyrin.stt.transcript import TranscriptStatus, TranscriptUpdate


class CommandCoordinator:
    """Track one STT stream and its dialogue reference across pauses.

    Candidate updates are advisory and never execute actions. A consumer must
    use (stream_id, segment_id) to replace them with later decisions.
    """

    def __init__(
        self,
        interpreter: CommandInterpreter,
        *,
        fragment_buffer: CommandFragmentBuffer | None = None,
        recent_utterances: Callable[[], tuple[str, ...]] | None = None,
    ) -> None:
        self.interpreter = interpreter
        self._fragments = fragment_buffer or CommandFragmentBuffer()
        self._recent_utterances = recent_utterances
        self._stream_id = 0
        self._segment_id: int | None = None
        self._finalized_through = -1
        self._emitted_candidate: CommandIntent | None = None
        self._pending: PendingCommandClarification | None = None
        self._last_referenced_app: str | None = None
        self._last_scroll: tuple[str, CommandKind, int | None, float] | None = None

    @property
    def pending_clarification(
        self,
    ) -> PendingCommandClarification | None:
        return self._pending

    @property
    def last_referenced_app(self) -> str | None:
        return self._last_referenced_app

    def cancel_fragment(self) -> None:
        """Discard an unfinished operation when another dialogue flow takes over."""
        self._fragments.clear()

    def cancel_dialogue(self) -> None:
        """Drop a pending question when normal command listening is paused."""
        self._pending = None
        self._fragments.clear()

    def start_new_stream(self) -> Sequence[CommandEvent]:
        """Reset segment IDs after STT reconnect; keep the pending dialogue."""
        events: tuple[CommandEvent, ...] = ()
        if self._segment_id is not None and self._emitted_candidate is not None:
            events = (
                CommandCandidateUpdate(
                    self._segment_id, None, stream_id=self._stream_id
                ),
            )
        self._stream_id += 1
        self._segment_id = None
        self._finalized_through = -1
        self._clear_candidate()
        self._fragments.clear()
        return events

    def observe(
        self,
        update: TranscriptUpdate,
        *,
        observed_active_app: str | None = None,
    ) -> Sequence[CommandEvent]:
        """Observe one update; pass a fresh OS observation, never cached context."""
        if update.segment_id <= self._finalized_through:
            return ()
        if self._segment_id is not None and update.segment_id < self._segment_id:
            return ()

        events: list[CommandEvent] = []
        if self._segment_id != update.segment_id:
            if self._segment_id is not None and self._emitted_candidate is not None:
                events.append(
                    CommandCandidateUpdate(
                        self._segment_id, None, stream_id=self._stream_id
                    )
                )
            self._segment_id = update.segment_id
            self._clear_candidate()

        if (
            update.status is TranscriptStatus.FINAL
            and self._fragments.hold(update.text)
        ):
            # A fresh operation supersedes an older yes/no question.
            self._pending = None
            events.append(
                CommandResolution(
                    update.segment_id,
                    None,
                    stream_id=self._stream_id,
                    language=update.language,
                )
            )
            self._finalized_through = update.segment_id
            self._segment_id = None
            self._clear_candidate()
            return tuple(events)

        interpreted_text = update.text
        if update.status is TranscriptStatus.FINAL:
            interpreted_text = self._fragments.combine(update.text) or update.text
        recent_scroll_kind: CommandKind | None = None
        recent_scroll_steps: int | None = None
        if self._last_scroll is not None and observed_active_app is not None:
            scroll_app, scroll_kind, scroll_steps, recorded_at = self._last_scroll
            if scroll_app == observed_active_app and monotonic() - recorded_at <= 30:
                recent_scroll_kind = scroll_kind
                recent_scroll_steps = scroll_steps
        interpretation = self.interpreter.interpret(
            interpreted_text,
            language=update.language,
            context=CommandContext(
                self._last_referenced_app,
                observed_active_app,
                update.status is TranscriptStatus.FINAL,
                self._recent_utterances()
                if update.status is TranscriptStatus.FINAL
                and self._recent_utterances is not None
                else (),
                recent_scroll_kind,
                recent_scroll_steps,
            ),
            pending=self._pending,
        )
        if update.status is TranscriptStatus.PARTIAL:
            intent = (
                interpretation.intent
                if isinstance(interpretation, ReadyCommand)
                else None
            )
            if intent != self._emitted_candidate:
                events.append(
                    CommandCandidateUpdate(
                        update.segment_id, intent, stream_id=self._stream_id
                    )
                )
                self._emitted_candidate = intent
            return tuple(events)

        intent = (
            interpretation.intent if isinstance(interpretation, ReadyCommand) else None
        )
        if isinstance(interpretation, ReadyPlan):
            if self._emitted_candidate is not None:
                events.append(
                    CommandCandidateUpdate(
                        update.segment_id, None, stream_id=self._stream_id
                    )
                )
            events.append(
                CommandPlanResolution(
                    update.segment_id,
                    interpretation.plan,
                    stream_id=self._stream_id,
                    language=update.language,
                )
            )
        else:
            events.append(
                CommandResolution(
                    update.segment_id,
                    intent,
                    stream_id=self._stream_id,
                    language=update.language,
                )
            )
        if isinstance(interpretation, (ReadyCommand, ReadyPlan)):
            self._pending = (
                interpretation.follow_up
                if isinstance(interpretation, ReadyCommand)
                else None
            )
            intents = (
                interpretation.plan.steps
                if isinstance(interpretation, ReadyPlan)
                else (interpretation.intent,)
            )
            for item in intents:
                if item.kind in (CommandKind.SCROLL_UP, CommandKind.SCROLL_DOWN):
                    self._last_scroll = (
                        item.target, item.kind, item.scroll_steps, monotonic()
                    )
                else:
                    self._last_scroll = None
                if item.kind in (
                    CommandKind.OPEN_APP,
                    CommandKind.RESTORE_APP,
                    CommandKind.NEW_APP_WINDOW,
                    CommandKind.NEW_APP_TAB,
                    CommandKind.APP_PREFERENCES,
                ):
                    self._last_referenced_app = item.target
                elif item.kind is CommandKind.OPEN_CHAT:
                    self._last_referenced_app = item.app
            if isinstance(self._pending, PendingWindowSelection):
                events.append(
                    ResponseRequest(
                        update.segment_id,
                        ResponseKind.CHOOSE_WINDOW,
                        ResponseChannel.TEXT_ONLY,
                        stream_id=self._stream_id,
                        target=self._pending.app_candidate.display_name,
                        window_count=self._pending.count,
                        language=update.language,
                    )
                )
        elif isinstance(interpretation, NeedsClarification):
            self._pending = interpretation.pending
            if isinstance(interpretation.pending, PendingIntentClarification):
                events.append(
                    ResponseRequest(
                        update.segment_id,
                        ResponseKind.CHOOSE_APP_OR_CHAT,
                        ResponseChannel.TEXT_AND_VOICE,
                        stream_id=self._stream_id,
                        target=interpretation.pending.app_candidate.display_name,
                        language=update.language,
                    )
                )
            elif isinstance(interpretation.pending, PendingAppClarification):
                candidates = interpretation.pending.candidates
                confirm = interpretation.pending.confirmation
                close_app = (
                    interpretation.pending.operation is CommandKind.CLOSE_APP_WINDOW
                )
                events.append(
                    ResponseRequest(
                        update.segment_id,
                        (
                            ResponseKind.CONFIRM_ACTION
                            if close_app and confirm
                            else ResponseKind.CONFIRM_APP
                            if confirm
                            else ResponseKind.CHOOSE_APP
                        ),
                        ResponseChannel.TEXT_ONLY,
                        stream_id=self._stream_id,
                        target=candidates[0].display_name if confirm else None,
                        app_candidates=(
                            ()
                            if confirm
                            else tuple(item.display_name for item in candidates)
                        ),
                        operation_candidates=(
                            (CommandKind.CLOSE_APP_WINDOW,) if close_app else ()
                        ),
                        language=update.language,
                    )
                )
            elif isinstance(interpretation.pending, PendingOperationClarification):
                events.append(
                    ResponseRequest(
                        update.segment_id,
                        ResponseKind.CHOOSE_OPERATION,
                        ResponseChannel.TEXT_AND_VOICE,
                        stream_id=self._stream_id,
                        target=interpretation.pending.app_candidate.display_name,
                        operation_candidates=interpretation.pending.options,
                        language=update.language,
                    )
                )
            elif isinstance(interpretation.pending, PendingActionConfirmation):
                events.append(
                    ResponseRequest(
                        update.segment_id,
                        ResponseKind.CONFIRM_ACTION,
                        ResponseChannel.TEXT_AND_VOICE,
                        stream_id=self._stream_id,
                        target=interpretation.pending.app_candidate.display_name,
                        operation_candidates=(interpretation.pending.operation,),
                        language=update.language,
                    )
                )
            elif isinstance(interpretation.pending, PendingNumberedCloseConfirmation):
                events.append(ResponseRequest(
                    update.segment_id,
                    ResponseKind.CONFIRM_NUMBERED_CLOSE,
                    ResponseChannel.TEXT_AND_VOICE,
                    stream_id=self._stream_id,
                    target=interpretation.pending.app_candidate.display_name,
                    window_index=interpretation.pending.window_index,
                    language=update.language,
                ))
            elif isinstance(interpretation.pending, PendingWindowSelection):
                events.append(
                    ResponseRequest(
                        update.segment_id,
                        ResponseKind.CHOOSE_WINDOW,
                        ResponseChannel.TEXT_ONLY,
                        stream_id=self._stream_id,
                        target=interpretation.pending.app_candidate.display_name,
                        window_count=interpretation.pending.count,
                        language=update.language,
                    )
                )
            elif isinstance(interpretation.pending, PendingClarification):
                events.append(
                    ResponseRequest(
                        update.segment_id,
                        ResponseKind.CHOOSE_CHAT_APP,
                        ResponseChannel.TEXT_AND_VOICE,
                        stream_id=self._stream_id,
                        target=interpretation.pending.target,
                        app_candidates=interpretation.pending.candidates,
                        language=update.language,
                    )
                )
        elif isinstance(interpretation, DeclinedClarification):
            self._pending = None
        elif isinstance(interpretation, ConversationalReply):
            voice_available = (update.language or "").split("-", 1)[0] in {
                "en",
                "fa",
            }
            events.append(
                ResponseRequest(
                    update.segment_id,
                    ResponseKind.CONVERSATION,
                    ResponseChannel.TEXT_AND_VOICE
                    if voice_available
                    else ResponseChannel.TEXT_ONLY,
                    stream_id=self._stream_id,
                    language=update.language,
                    message=interpretation.text,
                )
            )
        elif isinstance(interpretation, WakeOnly):
            events.append(
                ResponseRequest(
                    update.segment_id,
                    ResponseKind.READY_FOR_COMMAND,
                    ResponseChannel.TEXT_ONLY,
                    stream_id=self._stream_id,
                    language=update.language,
                )
            )
        elif isinstance(interpretation, (IncompleteCommand, UnrecognizedCommand)):
            # A fresh, unclear utterance supersedes any older confirmation.
            # Otherwise a later "yes" could authorize a stale app suggestion.
            self._pending = None
            events.append(
                ResponseRequest(
                    update.segment_id,
                    ResponseKind.REPEAT_COMMAND,
                    ResponseChannel.TEXT_ONLY,
                    stream_id=self._stream_id,
                    language=update.language,
                )
            )
        self._finalized_through = update.segment_id
        self._segment_id = None
        self._clear_candidate()
        return tuple(events)

    def _clear_candidate(self) -> None:
        self._emitted_candidate = None
