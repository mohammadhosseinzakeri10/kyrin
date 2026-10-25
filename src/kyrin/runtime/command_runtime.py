"""Connect live speech, command decisions, and bounded desktop actions.

The caller supplies the audio session, concrete adapters, and presentation.
This runtime owns event routing, ordered understanding, and optional actions.
"""

import logging
import sqlite3
from collections.abc import Callable, Generator
from contextlib import closing
from dataclasses import replace
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
from kyrin.audio.audio_errors import AudioQueueOverflowError
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
from kyrin.runtime.listening_diagnostics import ListeningDiagnostics
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
        self.listening_diagnostics = ListeningDiagnostics()
        self._voice_state = VoiceModeChanged(
            VoiceMode.STANDBY if voice_standby else VoiceMode.ACTIVE,
            source="startup",
            reason="configured_initial_mode",
            session_id=self.listening_diagnostics.session_id,
        )
        self.listening_diagnostics.state(
            "mode",
            self._voice_state.mode.value,
            reason="configured_initial_mode",
            source="startup",
        )
        self._last_mode_request_ns = 0
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
                self._understanding_failed,
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
            self.listening_diagnostics.state(
                "action",
                "busy",
                reason="execution_started",
                source="worker",
            )
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
                self.listening_diagnostics.state(
                    "action",
                    "idle",
                    reason="execution_returned",
                    source="worker",
                )

    def _understanding_failed(self) -> None:
        self.listening_diagnostics.state(
            "understanding",
            "failed",
            reason="worker_error",
            source="error",
        )
        self._controller.stop()

    def stop(self) -> None:
        self.listening_diagnostics.state(
            "runtime",
            "stopping",
            reason="stop_requested",
            source="controller",
        )
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

    @property
    def speech_generation(self) -> int:
        return self._history_stream_id

    def voice_mode_state(self) -> VoiceModeChanged:
        """Authoritative immutable snapshot, also used to reject queued UI events."""
        with self._voice_lock:
            return self._voice_state

    def set_commands_active(
        self,
        active: bool,
        *,
        source: str = "gui",
        reason: str = "explicit_control",
    ) -> None:
        self._change_voice_mode(
            VoiceMode.ACTIVE if active else VoiceMode.STANDBY,
            source=source,
            reason=reason,
        )

    def _change_voice_mode(
        self,
        mode: VoiceMode,
        *,
        source: str,
        reason: str,
        expected: VoiceModeChanged | None = None,
        segment_id: int | None = None,
    ) -> VoiceModeChanged | None:
        with self._voice_lock:
            previous = self._voice_state
            if self._stop_requested.is_set() or (
                expected is not None and expected is not previous
            ):
                return None
            state = VoiceModeChanged(
                mode,
                previous.mode,
                source,
                reason,
                previous.session_id,
                self._history_stream_id,
                previous.revision + 1,
                segment_id,
            )
            self._voice_state = state
            if source != "voice":
                self._last_mode_request_ns = self._clock_ns()
            self.listening_diagnostics.state(
                "mode",
                mode.value,
                reason=reason,
                source=source,
                generation=self._history_stream_id,
            )
            if mode is not VoiceMode.ACTIVE:
                self._reset_dialogue = True
        # Do not nest the mode lock with worker delivery/invalidation locks.
        if mode is not VoiceMode.ACTIVE:
            if self._worker is not None:
                self._worker.invalidate_pending()
            if self._understanding is not None:
                self._understanding.invalidate()
        return state

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
        state = self.voice_mode_state()
        active = state.mode is VoiceMode.ACTIVE
        if state.mode is VoiceMode.OFF:
            return True
        if event.status is not TranscriptStatus.FINAL:
            return not active
        mode = control_phrase(event.text, active=active)
        if mode is None:
            return not active
        with self._voice_lock:
            if (
                event.emitted_ns is not None
                and event.emitted_ns < self._last_mode_request_ns
            ):
                self.listening_diagnostics.pulse("stale_voice_control")
                return True
        if mode is state.mode:
            return True
        changed = self._change_voice_mode(
            mode,
            source="voice",
            reason="exact_final_control",
            expected=state,
            segment_id=event.segment_id,
        )
        if changed is None:
            return True
        self._clear_dialogue_if_requested()
        self._on_live_event(event)
        if self._on_voice_mode is not None:
            self._on_voice_mode(changed)
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
        self.listening_diagnostics.state(
            "runtime",
            "running",
            reason="run_started",
            source="controller",
        )
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
                        if isinstance(event.error, AudioQueueOverflowError):
                            overflow = event.error
                            self.listening_diagnostics.state(
                                "overflow",
                                f"{overflow.buffer} pending={overflow.pending} "
                                f"limit={overflow.limit} unit={overflow.unit}",
                                reason="bounded_audio_queue_full",
                                source="audio",
                                generation=self._history_stream_id,
                            )
                        self.listening_diagnostics.state(
                            "stt",
                            "retrying"
                            if event.retry_delay_s is not None
                            else "failed"
                            if event.error is not None
                            else "ended",
                            reason=type(event.error).__name__
                            if event.error is not None
                            else "end_of_input",
                            source="error" if event.error else "stt",
                            generation=self._history_stream_id,
                        )
                        self.listening_diagnostics.state(
                            "capture",
                            "end_reported",
                            reason="speech_session_ended",
                            source="stt",
                            generation=self._history_stream_id,
                        )
                        if not (
                            self._finite_source
                            and event.error is None
                            and event.retry_delay_s is None
                        ):
                            self._end_stream()
                        self._on_session_end(
                            replace(
                                event,
                                session_id=self.listening_diagnostics.session_id,
                            )
                        )
                        continue
                    self.listening_diagnostics.pulse("speech_event")
                    if isinstance(event, TranscriptUpdate):
                        self.listening_diagnostics.pulse(event.status.value)
                        if self._control_speech(event):
                            continue
                    else:
                        with self._voice_lock:
                            if self._voice_state.mode is not VoiceMode.ACTIVE:
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
                        if (
                            self._voice_state.mode is not VoiceMode.ACTIVE
                            or self._stop_requested.is_set()
                        ):
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
            self.listening_diagnostics.state(
                "runtime",
                "draining",
                reason="input_ended" if exhausted else "processing_error",
                source="stt" if exhausted else "error",
            )
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
                self.listening_diagnostics.state(
                    "runtime",
                    "exiting",
                    reason="run_finally",
                    source="controller",
                )
                if self._telegram_selection is not None:
                    self._telegram_selection.cancel()

    def _understanding_overload(self, event: TranscriptUpdate) -> None:
        self.listening_diagnostics.pulse("understanding_overload")
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
        self.listening_diagnostics.state(
            "understanding",
            "busy",
            reason="work_started",
            source="worker",
            generation=generation,
        )
        try:
            return self._understand_command(coordinator, event, generation)
        finally:
            self.listening_diagnostics.state(
                "understanding",
                "idle",
                reason="work_returned",
                source="worker",
                generation=generation,
            )
            self.listening_diagnostics.pulse("understanding_returned")

    def _understand_command(
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
