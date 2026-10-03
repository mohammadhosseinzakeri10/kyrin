"""Turn revisable transcript updates into safe, observable command decisions."""

from collections.abc import Sequence

from kyrin.commands.interpreter import (
    CommandInterpreter,
    IncompleteCommand,
    NeedsClarification,
    ReadyCommand,
    UnrecognizedCommand,
)
from kyrin.commands.models import (
    CommandCandidateUpdate,
    CommandContext,
    CommandEvent,
    CommandIntent,
    CommandKind,
    CommandResolution,
    PendingClarification,
    ResponseChannel,
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
        self._pending: PendingClarification | None = None
        self._last_referenced_app: str | None = None

    @property
    def pending_clarification(self) -> PendingClarification | None:
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
        events.append(
            CommandResolution(update.segment_id, intent, stream_id=self._stream_id)
        )
        if isinstance(interpretation, ReadyCommand):
            self._pending = None
            if intent is not None:
                if intent.kind is CommandKind.OPEN_APP:
                    self._last_referenced_app = intent.target
                elif intent.kind is CommandKind.OPEN_CHAT:
                    self._last_referenced_app = intent.app
        elif isinstance(interpretation, NeedsClarification):
            self._pending = interpretation.pending
            events.append(
                ResponseRequest(
                    update.segment_id,
                    interpretation.pending.question,
                    ResponseChannel.TEXT_AND_VOICE,
                    stream_id=self._stream_id,
                )
            )
        elif isinstance(interpretation, (IncompleteCommand, UnrecognizedCommand)):
            events.append(
                ResponseRequest(
                    update.segment_id,
                    "متوجه نشدم. لطفاً فرمان را دوباره بگویید.",
                    ResponseChannel.TEXT_AND_VOICE,
                    stream_id=self._stream_id,
                )
            )
        self._finalized_through = update.segment_id
        self._segment_id = None
        self._clear_candidate()
        return tuple(events)

    def _clear_candidate(self) -> None:
        self._emitted_candidate = None
