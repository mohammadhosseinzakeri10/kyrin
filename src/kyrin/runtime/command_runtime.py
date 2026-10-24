"""Connect live speech, command decisions, and bounded desktop actions.

The caller supplies the audio session, concrete adapters, and presentation.
This runtime owns event routing, ordered understanding, and optional actions.
"""

import logging
import sqlite3
from collections.abc import Callable, Generator
from contextlib import closing
from datetime import UTC, datetime
from functools import partial
from threading import Event, Lock
from time import perf_counter_ns
from typing import Protocol
from uuid import uuid4

from kyrin.actions.cancellation import ActionCancelled, ActionExecutionContext
from kyrin.actions.executor import ActionExecutor, execute_with_unknown_fallback
from kyrin.actions.gate import ActionGate
from kyrin.actions.models import (
    ActionDecision,
    ActionFeedback,
    ActionKey,
    ActionNotice,
    ActionNoticeReason,
    ActionOutcome,
)
from kyrin.actions.plan_runner import ActionPlanRunner
from kyrin.actions.queued_dispatch import (
    ActionOutput,
    FinalActionCommand,
    QueuedActionDispatcher,
)
from kyrin.actions.telegram_selection import TelegramChatSelection
from kyrin.audio.live_speech_pipeline import LiveSpeechEvent
from kyrin.commands.coordinator import CommandCoordinator
from kyrin.commands.models import (
    CommandEvent,
    CommandPlanResolution,
    CommandResolution,
    ResponseChannel,
    ResponseKind,
    ResponseRequest,
)
from kyrin.desktop.active_app import ActiveAppObserver
from kyrin.desktop.command_bridge import observe_command_update
from kyrin.memory.history import ConversationHistory, ConversationTurn
from kyrin.runtime.command_worker import (
    CommandUnderstandingWorker,
    CommandWork,
    UnderstoodCommand,
)
from kyrin.runtime.speech_sessions import SpeechRuntimeEvent, SpeechSessionEnded
from kyrin.runtime.voice_control import VoiceMode, VoiceModeChanged, control_phrase
from kyrin.stt.transcript import TranscriptStatus, TranscriptUpdate
from kyrin.system_power.flow import SystemPowerFlow
from kyrin.timing import Temperature, TimingEvent, TimingScope, mark, timing_scope

_LOGGER = logging.getLogger(__name__)
_FILE_ACTION_DRAIN_TIMEOUT_S = 60.0


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
    *,
    context: ActionExecutionContext | None = None,
) -> tuple[ActionOutput, ...]:
    """Execute one final decision on the worker that owns the action gate."""
    if isinstance(event, CommandPlanResolution):
        return ActionPlanRunner(
            gate, executor, observe_active_app=observe_active_app
        ).run(event, context=context)
    if context is not None and context.cancelled and event.intent is not None:
        return (
            ActionNotice(
                ActionKey(event.stream_id, event.segment_id, event.step_index),
                event.intent,
                ActionNoticeReason.CANCELLED,
                language=event.language,
            ),
        )
    decision = gate.observe(event)
    if decision is None:
        return ()
    if isinstance(decision, ActionNotice):
        return (decision,)
    if context is not None and context.cancelled:
        return (gate.cancel_unstarted(decision.key),)
    try:
        result = execute_with_unknown_fallback(executor, decision, context=context)
    except ActionCancelled:
        return (gate.cancel_unstarted(decision.key),)
    feedback = gate.record_result(result)
    mark("feedback", key=feedback.key)
    if result.outcome is ActionOutcome.CONFIRMED:
        mark("postcondition_observed", key=feedback.key)
    return (feedback,)


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
        scroll_focus_reader: Callable[[], tuple[str, int] | None] | None = None,
        system_power: SystemPowerFlow | None = None,
        telegram_selection: TelegramChatSelection | None = None,
        history: ConversationHistory | None = None,
        voice_standby: bool = False,
        on_voice_mode: Callable[[VoiceModeChanged], None] | None = None,
        finite_source: bool = False,
        on_timing: Callable[[TimingEvent], None] | None = None,
        clock_ns: Callable[[], int] = perf_counter_ns,
        timing_temperature: Temperature = "unknown",
    ) -> None:
        if (coordinator is None) != (gate is None):
            raise ValueError("coordinator and action gate must be supplied together")
        if executor is not None and gate is None:
            raise ValueError("action executor requires a command coordinator")
        self._controller = controller
        self._gate = gate
        self._observer = observer
        self._on_live_event = on_live_event
        self._on_command_event = on_command_event
        self._on_action_output = on_action_output
        self._on_session_end = on_session_end
        self._on_active_app = on_active_app
        self._scroll_focus_reader = scroll_focus_reader
        self._system_power = system_power
        self._telegram_selection = telegram_selection
        self._history = history
        self._history_session_id = uuid4().hex
        self._on_timing = on_timing
        self._clock_ns = clock_ns
        self._timing_temperature = timing_temperature
        self._history_stream_id = 0
        self._voice_lock = Lock()
        self._commands_active = not voice_standby
        self._reset_dialogue = False
        self._on_voice_mode = on_voice_mode
        self._finite_source = finite_source
        self._stop_requested = Event()
        self._worker = (
            QueuedActionDispatcher(
                lambda command, context: self._execute_timed(
                    command, context, gate, executor
                ),
                on_action_output,
                on_timing=self._action_timing,
            )
            if executor is not None and gate is not None
            else None
        )

        self._understanding = (
            CommandUnderstandingWorker(
                coordinator,
                self._understand,
                self._on_understood,
                self._controller.stop,
            )
            if coordinator is not None
            else None
        )

    def _timing_scope(self, key: ActionKey, route: str = "command") -> TimingScope:
        return TimingScope(
            self._history_session_id,
            key,
            self._on_timing or (lambda event: None),
            self._clock_ns,
            ("file/" if self._finite_source else "live/") + route,
            self._timing_temperature,
        )

    def _transcript_timing(self, event: TranscriptUpdate) -> TimingScope | None:
        if self._on_timing is None or event.status is not TranscriptStatus.FINAL:
            return None
        scope = self._timing_scope(ActionKey(self._history_stream_id, event.segment_id))
        if event.timing is not None:
            for stage, at_ns in event.timing.stamps:
                scope.mark(stage, at_ns=at_ns)
        scope.mark("final", at_ns=event.emitted_ns)
        return scope

    def _action_timing(self, command: FinalActionCommand, stage: str) -> None:
        route = (
            "plan"
            if isinstance(command, CommandPlanResolution)
            else (
                command.intent.kind.value if command.intent is not None else "command"
            )
        )
        self._timing_scope(
            ActionKey(command.stream_id, command.segment_id), route
        ).mark(stage)

    def _execute_timed(
        self,
        command: FinalActionCommand,
        context: ActionExecutionContext,
        gate: ActionGate,
        executor: ActionExecutor,
    ) -> tuple[ActionOutput, ...]:
        route = (
            "plan"
            if isinstance(command, CommandPlanResolution)
            else (
                command.intent.kind.value if command.intent is not None else "command"
            )
        )
        scope = self._timing_scope(
            ActionKey(command.stream_id, command.segment_id), route
        )
        with timing_scope(scope):
            scope.mark("action_started")
            try:
                return execute_final_command(
                    command,
                    gate,
                    executor,
                    self._observer.observe_active_app if self._observer else None,
                    context=context,
                )
            finally:
                scope.mark("command_completed")

    def stop(self) -> None:
        self._stop_requested.set()
        if self._worker is not None:
            self._worker.invalidate_pending()
        if self._understanding is not None:
            self._understanding.request_stop()
        if self._telegram_selection is not None:
            self._telegram_selection.cancel()
        if self._system_power is not None:
            self._system_power.cancel()
        self._controller.stop()

    def set_commands_active(self, active: bool) -> None:
        """Let the GUI button switch modes without rebuilding the STT session."""
        with self._voice_lock:
            self._commands_active = active
            if not active:
                self._reset_dialogue = True
                if self._worker is not None:
                    self._worker.invalidate_pending()
                if self._understanding is not None:
                    self._understanding.invalidate()

    def _clear_dialogue_if_requested(self) -> None:
        with self._voice_lock:
            reset = self._reset_dialogue
            self._reset_dialogue = False
        if not reset:
            return
        if self._telegram_selection is not None:
            self._telegram_selection.cancel()
        if self._system_power is not None:
            self._system_power.cancel()

    def _control_speech(self, event: TranscriptUpdate) -> bool:
        with self._voice_lock:
            active = self._commands_active
        if event.status is not TranscriptStatus.FINAL:
            return not active
        mode = control_phrase(event.text, active=active)
        if mode is None:
            return not active
        if (mode is VoiceMode.ACTIVE and active) or (
            mode is VoiceMode.STANDBY and not active
        ):
            return True
        if mode is not VoiceMode.OFF:
            self.set_commands_active(mode is VoiceMode.ACTIVE)
        else:
            self.set_commands_active(False)
        self._clear_dialogue_if_requested()
        self._on_live_event(event)
        if self._on_voice_mode is not None:
            self._on_voice_mode(VoiceModeChanged(mode))
        return True

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
        understanding = self._understanding
        exhausted = False
        try:
            if worker is not None:
                worker.start()
            if understanding is not None:
                understanding.start()
            with closing(self._controller.events()) as stream:
                for event in stream:
                    if self._stop_requested.is_set():
                        break
                    generation = worker.generation if worker is not None else 0
                    understanding_generation = (
                        understanding.generation if understanding is not None else 0
                    )
                    self._clear_dialogue_if_requested()
                    if isinstance(event, SpeechSessionEnded):
                        if not (
                            self._finite_source
                            and event.error is None
                            and event.retry_delay_s is None
                        ):
                            self._end_stream()
                        self._on_session_end(event)
                        continue
                    if isinstance(event, TranscriptUpdate):
                        if self._control_speech(event):
                            continue
                    else:
                        with self._voice_lock:
                            if not self._commands_active:
                                continue
                    timing = (
                        self._transcript_timing(event)
                        if isinstance(event, TranscriptUpdate)
                        else None
                    )
                    self._on_live_event(event)
                    if understanding is None or not isinstance(event, TranscriptUpdate):
                        continue
                    with self._voice_lock:
                        if not self._commands_active or self._stop_requested.is_set():
                            continue
                    accepted = understanding.submit(
                        CommandWork(
                            event,
                            generation,
                            self._history_stream_id,
                            timing,
                        ),
                        generation=understanding_generation,
                        wait_for_capacity=(
                            self._finite_source
                            and event.status is TranscriptStatus.FINAL
                        ),
                    )
                    if not accepted and event.status is TranscriptStatus.FINAL:
                        understanding.publish(
                            understanding_generation,
                            partial(self._understanding_overload, event),
                        )
            exhausted = True
        finally:
            drain = exhausted and not self._stop_requested.is_set()
            understanding_done = False
            try:
                try:
                    if not drain and worker is not None:
                        worker.invalidate_pending()
                    if understanding is not None:
                        understanding.close(
                            drain=drain,
                            timeout_s=(_FILE_ACTION_DRAIN_TIMEOUT_S if drain else 1.0),
                        )
                    understanding_done = True
                finally:
                    try:
                        if worker is not None:
                            worker.close(
                                drain=(
                                    self._finite_source
                                    and drain
                                    and understanding_done
                                    and not self._stop_requested.is_set()
                                ),
                                timeout_s=(
                                    _FILE_ACTION_DRAIN_TIMEOUT_S
                                    if self._finite_source
                                    else 20.0
                                ),
                            )
                    finally:
                        self._end_stream()
            finally:
                if self._telegram_selection is not None:
                    self._telegram_selection.cancel()

    def _understanding_overload(self, event: TranscriptUpdate) -> None:
        _LOGGER.warning("Command understanding queue is full")
        self._on_command_event(
            ResponseRequest(
                event.segment_id,
                ResponseKind.REPEAT_COMMAND,
                ResponseChannel.TEXT_AND_VOICE,
                stream_id=self._history_stream_id,
                language=event.language,
            )
        )

    def _understand(
        self,
        coordinator: CommandCoordinator,
        event: TranscriptUpdate,
        generation: int,
    ) -> tuple[str | None, tuple[CommandEvent, ...]]:
        understanding = self._understanding
        assert understanding is not None
        consumed = False

        def route_dialogue() -> None:
            nonlocal consumed
            if event.status is not TranscriptStatus.FINAL:
                return
            consumed = (
                self._system_power is not None
                and self._system_power.on_final_speech(event.text)
            ) or (
                self._telegram_selection is not None
                and self._telegram_selection.on_final_speech(event.text)
            )
            if consumed:
                coordinator.cancel_fragment()

        if not understanding.publish(generation, route_dialogue) or consumed:
            return None, ()
        active_app, decisions = observe_command_update(
            coordinator, event, self._observer, self._scroll_focus_reader
        )
        return active_app, tuple(decisions)

    def _on_understood(self, result: UnderstoodCommand) -> None:
        understanding = self._understanding
        assert understanding is not None
        event = result.work.update
        if (
            self._observer is not None
            and event.status is TranscriptStatus.FINAL
            and self._on_active_app is not None
        ):
            callback = self._on_active_app
            understanding.publish(
                result.generation, lambda: callback(result.active_app)
            )
        for decision in result.decisions:
            if not understanding.publish(
                result.generation, partial(self._on_command_event, decision)
            ):
                return
            if self._worker is not None and isinstance(
                decision, (CommandResolution, CommandPlanResolution)
            ):
                # Capacity waits must stay outside the publication lock so
                # stop can invalidate both queues and wake a finite producer.
                notice = self._worker.submit(
                    decision,
                    wait_for_capacity=self._finite_source,
                    generation=result.work.action_generation,
                )
                if notice is not None:
                    understanding.publish(
                        result.generation, partial(self._on_action_output, notice)
                    )
            elif self._worker is None:
                assert self._gate is not None
                understanding.publish(
                    result.generation, partial(self._dispatch_dry_run, decision)
                )
        understanding.publish(
            result.generation,
            lambda: self._remember(event, stream_id=result.work.stream_id),
        )

    def _dispatch_dry_run(self, decision: CommandEvent) -> None:
        assert self._gate is not None
        for action in dispatch_command_action(decision, self._gate, None):
            self._on_action_output(action)

    def _end_stream(self) -> None:
        if self._system_power is not None:
            self._system_power.cancel()
        if self._worker is not None:
            self._worker.invalidate_pending()
        if self._understanding is not None:
            for decision in self._understanding.invalidate(
                new_stream=True, clear_dialogue=False
            ):
                self._on_command_event(decision)
            self._history_stream_id += 1

    def _remember(
        self, event: TranscriptUpdate, *, stream_id: int | None = None
    ) -> None:
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
                    self._history_stream_id if stream_id is None else stream_id,
                    event.segment_id,
                )
            )
        except (OSError, RuntimeError, sqlite3.Error) as exc:
            _LOGGER.warning("Conversation history is unavailable: %s", exc)
