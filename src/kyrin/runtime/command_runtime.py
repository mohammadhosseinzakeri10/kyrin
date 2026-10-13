"""Connect live speech, command decisions, and bounded desktop actions.

The caller supplies the audio session, concrete adapters, and presentation.
This runtime owns only event routing and its optional action worker.
"""

import logging
import sqlite3
from collections.abc import Callable, Generator
from contextlib import closing
from datetime import UTC, datetime
from typing import Protocol
from uuid import uuid4

from kyrin.actions.executor import ActionExecutor, execute_with_unknown_fallback
from kyrin.actions.gate import ActionGate
from kyrin.actions.models import ActionDecision, ActionFeedback, ActionNotice
from kyrin.actions.plan_runner import ActionPlanRunner
from kyrin.actions.queued_dispatch import (
    ActionOutput,
    FinalActionCommand,
    QueuedActionDispatcher,
)
from kyrin.audio.live_speech_pipeline import LiveSpeechEvent
from kyrin.commands.coordinator import CommandCoordinator
from kyrin.commands.models import (
    CommandEvent,
    CommandPlanResolution,
    CommandResolution,
)
from kyrin.desktop.active_app import ActiveAppObserver
from kyrin.desktop.command_bridge import observe_command_update
from kyrin.memory.history import ConversationHistory, ConversationTurn
from kyrin.runtime.speech_sessions import SpeechRuntimeEvent, SpeechSessionEnded
from kyrin.stt.transcript import TranscriptStatus, TranscriptUpdate
from kyrin.system_power.flow import SystemPowerFlow

_LOGGER = logging.getLogger(__name__)


def dispatch_command_action(
    event: CommandEvent,
    gate: ActionGate,
    executor: ActionExecutor | None,
) -> tuple[ActionDecision | ActionFeedback, ...]:
    """Apply final-command policy in dry run or execute with a supplied adapter."""
    if executor is not None:
        if isinstance(event, (CommandResolution, CommandPlanResolution)):
            return execute_final_command(event, gate, executor)
        return ()
    if isinstance(event, CommandPlanResolution):
        actions: list[ActionDecision] = []
        for index, step in enumerate(event.plan.steps):
            decision = gate.observe(
                CommandResolution(
                    event.segment_id,
                    step,
                    stream_id=event.stream_id,
                    language=event.language,
                    step_index=index,
                )
            )
            if decision is not None:
                actions.append(decision)
                if isinstance(decision, ActionNotice):
                    break
        return tuple(actions)

    decision = gate.observe(event)
    return () if decision is None else (decision,)


def execute_final_command(
    event: FinalActionCommand,
    gate: ActionGate,
    executor: ActionExecutor,
    observe_active_app: Callable[[], str | None] | None = None,
) -> tuple[ActionOutput, ...]:
    """Execute one final decision on the worker that owns the action gate."""
    if isinstance(event, CommandPlanResolution):
        return ActionPlanRunner(
            gate, executor, observe_active_app=observe_active_app
        ).run(event)
    decision = gate.observe(event)
    if decision is None:
        return ()
    if isinstance(decision, ActionNotice):
        return (decision,)
    return (gate.record_result(execute_with_unknown_fallback(executor, decision)),)


class SpeechEventSource(Protocol):
    def events(self) -> Generator[SpeechRuntimeEvent]: ...

    def stop(self) -> None: ...


class LiveCommandRuntime:
    """Run one listening session; pauses do not erase dialogue context.

    A final transcript may query desktop focus and enqueue an action. Partial
    transcripts cannot execute. stop() may be called from another thread.
    The application retains ownership of the STT engine and response speaker.
    """

    def __init__(
        self,
        controller: SpeechEventSource,
        *,
        coordinator: CommandCoordinator | None,
        gate: ActionGate | None,
        observer: ActiveAppObserver | None,
        executor: ActionExecutor | None,
        on_live_event: Callable[[LiveSpeechEvent], None],
        on_command_event: Callable[[CommandEvent], None],
        on_action_output: Callable[[ActionDecision | ActionFeedback], None],
        on_session_end: Callable[[SpeechSessionEnded], None],
        on_active_app: Callable[[str | None], None] | None = None,
        system_power: SystemPowerFlow | None = None,
        history: ConversationHistory | None = None,
    ) -> None:
        if (coordinator is None) != (gate is None):
            raise ValueError("coordinator and action gate must be supplied together")
        if executor is not None and gate is None:
            raise ValueError("action executor requires a command coordinator")
        self._controller = controller
        self._coordinator = coordinator
        self._gate = gate
        self._observer = observer
        self._on_live_event = on_live_event
        self._on_command_event = on_command_event
        self._on_action_output = on_action_output
        self._on_session_end = on_session_end
        self._on_active_app = on_active_app
        self._system_power = system_power
        self._history = history
        self._history_session_id = uuid4().hex
        self._history_stream_id = 0
        self._worker = (
            QueuedActionDispatcher(
                lambda command: execute_final_command(
                    command,
                    gate,
                    executor,
                    observer.observe_active_app if observer is not None else None,
                ),
                on_action_output,
            )
            if executor is not None and gate is not None
            else None
        )

    def stop(self) -> None:
        if self._system_power is not None:
            self._system_power.cancel()
        self._controller.stop()

    def respond_to_system_action(self, request_id: int, answer: str) -> bool:
        return (
            self._system_power.respond(request_id, answer)
            if self._system_power is not None
            else False
        )

    def expire_system_action(self) -> None:
        if self._system_power is not None:
            self._system_power.expire()

    def run(self) -> None:
        """Consume speech until stopped, exhausted, or a terminal failure."""
        worker = self._worker
        coordinator = self._coordinator
        try:
            if worker is not None:
                worker.start()
            with closing(self._controller.events()) as stream:
                for event in stream:
                    if isinstance(event, SpeechSessionEnded):
                        self._end_stream()
                        self._on_session_end(event)
                        continue
                    self._on_live_event(event)
                    if coordinator is None or not isinstance(event, TranscriptUpdate):
                        continue
                    if (
                        event.status is TranscriptStatus.FINAL
                        and self._system_power is not None
                        and self._system_power.on_final_speech(event.text)
                    ):
                        coordinator.cancel_fragment()
                        self._remember(event)
                        continue
                    active_app, decisions = observe_command_update(
                        coordinator, event, self._observer
                    )
                    if (
                        self._observer is not None
                        and event.status is TranscriptStatus.FINAL
                        and self._on_active_app is not None
                    ):
                        self._on_active_app(active_app)
                    for decision in decisions:
                        self._on_command_event(decision)
                        if worker is not None and isinstance(
                            decision, (CommandResolution, CommandPlanResolution)
                        ):
                            notice = worker.submit(decision)
                            if notice is not None:
                                self._on_action_output(notice)
                        elif worker is None:
                            assert self._gate is not None
                            for action in dispatch_command_action(
                                decision, self._gate, None
                            ):
                                self._on_action_output(action)
                    self._remember(event)
        finally:
            self._end_stream()
            if worker is not None:
                worker.close()

    def _end_stream(self) -> None:
        if self._system_power is not None:
            self._system_power.cancel()
        if self._coordinator is not None:
            for decision in self._coordinator.start_new_stream():
                self._on_command_event(decision)
            self._history_stream_id += 1

    def _remember(self, event: TranscriptUpdate) -> None:
        if (
            self._history is None
            or event.status is not TranscriptStatus.FINAL
            or not event.text.strip()
            or event.text.strip().startswith("[")
        ):
            return
        try:
            self._history.append(
                ConversationTurn(
                    event.text[:2000],
                    event.language,
                    datetime.now(UTC),
                    self._history_session_id,
                    self._history_stream_id,
                    event.segment_id,
                )
            )
        except (OSError, RuntimeError, sqlite3.Error) as exc:
            _LOGGER.warning("Conversation history is unavailable: %s", exc)
