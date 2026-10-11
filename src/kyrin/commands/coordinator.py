"""Turn revisable transcript updates into safe, observable command decisions."""

from collections.abc import Sequence

from kyrin.commands.interpreter import (
    CommandInterpreter,
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
    PendingAppClarification,
    PendingCommandClarification,
    PendingIntentClarification,
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

    def __init__(self, interpreter: CommandInterpreter) -> None:
        self.interpreter = interpreter
        self._stream_id = 0
        self._segment_id: int | None = None
        self._finalized_through = -1
        self._emitted_candidate: CommandIntent | None = None
        self._pending: PendingCommandClarification | None = None
        self._last_referenced_app: str | None = None

    @property
    def pending_clarification(
        self,
    ) -> PendingCommandClarification | None:
        return self._pending

    @property
    def last_referenced_app(self) -> str | None:
        return self._last_referenced_app

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

        interpretation = self.interpreter.interpret(
            update.text,
            language=update.language,
            context=CommandContext(self._last_referenced_app, observed_active_app),
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
            self._pending = None
            intents = (
                interpretation.plan.steps
                if isinstance(interpretation, ReadyPlan)
                else (interpretation.intent,)
            )
            for item in intents:
                if item.kind in (CommandKind.OPEN_APP, CommandKind.RESTORE_APP):
                    self._last_referenced_app = item.target
                elif item.kind is CommandKind.OPEN_CHAT:
                    self._last_referenced_app = item.app
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
                events.append(
                    ResponseRequest(
                        update.segment_id,
                        ResponseKind.CONFIRM_APP
                        if confirm
                        else ResponseKind.CHOOSE_APP,
                        ResponseChannel.TEXT_AND_VOICE,
                        stream_id=self._stream_id,
                        target=candidates[0].display_name if confirm else None,
                        app_candidates=(
                            ()
                            if confirm
                            else tuple(item.display_name for item in candidates)
                        ),
                        language=update.language,
                    )
                )
            else:
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
                    ResponseChannel.TEXT_AND_VOICE,
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
