"""Real model-assisted routing with blocked inference and no desktop or network."""

from collections.abc import Generator
from pathlib import Path
from queue import Queue
from threading import Event, Thread

import pytest

from kyrin.actions.gate import ActionGate, ActionPolicy
from kyrin.actions.models import ActionDecision, ActionFeedback, ActionRequest
from kyrin.commands.coordinator import CommandCoordinator
from kyrin.commands.interpreter import NotACommand
from kyrin.commands.model_interpreter import ModelAssistedInterpreter
from kyrin.commands.models import (
    CommandContext,
    CommandEvent,
    CommandResolution,
    PendingCommandClarification,
    ResponseKind,
    ResponseRequest,
)
from kyrin.commands.understanding import (
    ConfirmationDecision,
    MeaningStep,
    ProposedMeaning,
    RequestedOperation,
    UnderstandingInput,
    UnderstandingResult,
    UnderstandingStatus,
)
from kyrin.desktop.platforms.xdg import XdgDesktopAppCatalog
from kyrin.desktop.spoken_app_names import CatalogSpokenAppResolver
from kyrin.runtime.command_runtime import LiveCommandRuntime
from kyrin.runtime.speech_sessions import SpeechRuntimeEvent, SpeechSessionEnded
from kyrin.stt.errors import SpeechToTextError
from kyrin.stt.transcript import TranscriptStatus, TranscriptUpdate


class NoFastRule:
    """Force the injected model path while keeping real validation downstream."""

    def interpret(
        self,
        text: str,
        *,
        language: str | None,
        context: CommandContext,
        pending: PendingCommandClarification | None,
    ) -> NotACommand:
        return NotACommand()


class BlockingModel:
    def __init__(self) -> None:
        self.entered = Event()
        self.release = Event()
        self.calls: list[tuple[str, str | None]] = []

    def understand(
        self, source: UnderstandingInput, *, context: CommandContext
    ) -> UnderstandingResult:
        self.calls.append((source.text, context.last_referenced_app))
        if "Telegram" in source.text:
            self.entered.set()
            assert self.release.wait(5), "test did not release the model"
            target = "Telegram"
        else:
            target = "Browser"
        return UnderstandingResult(
            UnderstandingStatus.READY,
            (ProposedMeaning((MeaningStep(RequestedOperation.OPEN_APP, target),)),),
        )

    def classify_confirmation(
        self, source: UnderstandingInput, *, question: str
    ) -> ConfirmationDecision:
        raise AssertionError("no confirmation should be needed")


class Source:
    def __init__(self) -> None:
        self.queue: Queue[SpeechRuntimeEvent | None] = Queue()
        self.stopped = Event()

    def events(self) -> Generator[SpeechRuntimeEvent]:
        while (event := self.queue.get()) is not None:
            yield event

    def stop(self) -> None:
        self.stopped.set()
        self.queue.put(None)


def _final(segment: int, target: str = "Browser") -> TranscriptUpdate:
    # Explicit source-operation evidence and an exact installed model target.
    return TranscriptUpdate(segment, f"Open {target}", TranscriptStatus.FINAL, "en")


def _runtime(
    tmp_path: Path,
    source: Source,
    model: BlockingModel,
    commands: list[CommandEvent],
    actions: list[ActionDecision | ActionFeedback],
    ended: Event,
    *,
    finite_source: bool = False,
    overloaded: Event | None = None,
    producer_full: Event | None = None,
) -> LiveCommandRuntime:
    applications = tmp_path / "applications"
    applications.mkdir()
    for name in ("Telegram", "Browser"):
        (applications / f"{name.lower()}.desktop").write_text(
            f"[Desktop Entry]\nType=Application\nName={name}\n", encoding="utf-8"
        )
    names = CatalogSpokenAppResolver(
        XdgDesktopAppCatalog((tmp_path,)),
        {"telegram.desktop": "telegram", "browser.desktop": "browser"},
    )
    interpreter = ModelAssistedInterpreter(
        NoFastRule(),
        model,
        names,
        allowed_apps=frozenset({"telegram", "browser"}),
        supported_chat_apps=frozenset(),
    )

    def command(event: CommandEvent) -> None:
        commands.append(event)
        if overloaded is not None and isinstance(event, ResponseRequest):
            if event.kind is ResponseKind.REPEAT_COMMAND:
                overloaded.set()

    def live(event: SpeechRuntimeEvent) -> None:
        if producer_full is not None and isinstance(event, TranscriptUpdate):
            if event.segment_id == 5:
                producer_full.set()

    return LiveCommandRuntime(
        source,
        coordinator=CommandCoordinator(interpreter),
        gate=ActionGate(ActionPolicy(allowed_apps=frozenset({"telegram", "browser"}))),
        observer=None,
        executor=None,
        on_live_event=live,
        on_command_event=command,
        on_action_output=actions.append,
        on_session_end=lambda _: ended.set(),
        finite_source=finite_source,
    )


def _run(runtime: LiveCommandRuntime, errors: list[Exception]) -> Thread:
    def run() -> None:
        try:
            runtime.run()
        except Exception as exc:
            errors.append(exc)

    thread = Thread(target=run)
    thread.start()
    return thread


@pytest.mark.parametrize("transition", ("stop", "pause", "session"))
def test_blocked_model_cannot_publish_or_change_context_after_transition(
    tmp_path: Path,
    transition: str,
) -> None:
    model, source, ended = BlockingModel(), Source(), Event()
    commands: list[CommandEvent] = []
    actions: list[ActionDecision | ActionFeedback] = []
    errors: list[Exception] = []
    runtime = _runtime(tmp_path, source, model, commands, actions, ended)
    runner = _run(runtime, errors)
    try:
        source.queue.put(_final(0, "Telegram"))
        assert model.entered.wait(1), "utterance never reached the actual model path"
        if transition == "stop":
            runtime.stop()
            assert source.stopped.is_set()
        elif transition == "pause":
            runtime.set_commands_active(False)
            runtime.set_commands_active(True)
            source.queue.put(_final(1))
            source.queue.put(None)
        else:
            source.queue.put(SpeechSessionEnded(0, SpeechToTextError("retry"), 0))
            assert ended.wait(1), "session boundary waited behind inference"
            source.queue.put(_final(0))
            source.queue.put(None)
    finally:
        model.release.set()
        source.queue.put(None)
        runner.join(3)
    assert not runner.is_alive()
    assert errors == []
    if transition == "stop":
        assert commands == []
        assert actions == []
    else:
        assert [
            action.intent.target
            for action in actions
            if isinstance(action, ActionRequest)
        ] == ["browser"]
        assert len(model.calls) == 2
        assert model.calls[1][1] is None
        resolutions = [item for item in commands if isinstance(item, CommandResolution)]
        assert len(resolutions) == 1
        assert resolutions[0].stream_id == (1 if transition == "session" else 0)


def test_live_overload_is_visible_and_accepted_finals_keep_fifo(tmp_path: Path) -> None:
    model, source, overloaded = BlockingModel(), Source(), Event()
    commands: list[CommandEvent] = []
    actions: list[ActionDecision | ActionFeedback] = []
    errors: list[Exception] = []
    runtime = _runtime(
        tmp_path, source, model, commands, actions, Event(), overloaded=overloaded
    )
    runner = _run(runtime, errors)
    try:
        source.queue.put(_final(0, "Telegram"))
        assert model.entered.wait(1)
        for segment in range(1, 6):
            source.queue.put(_final(segment))
        assert overloaded.wait(1), "speech consumer blocked on the full queue"
    finally:
        model.release.set()
        source.queue.put(None)
        runner.join(3)
    assert not runner.is_alive()
    assert errors == []
    assert [
        item.segment_id for item in commands if isinstance(item, CommandResolution)
    ] == list(range(5))
    assert [
        item.segment_id for item in commands if isinstance(item, ResponseRequest)
    ] == [5]
    assert [
        item.key.segment_id for item in actions if isinstance(item, ActionRequest)
    ] == list(range(5))
    assert len(model.calls) == 5


def test_finite_source_stop_wakes_full_understanding_queue(tmp_path: Path) -> None:
    model, source, full = BlockingModel(), Source(), Event()
    commands: list[CommandEvent] = []
    actions: list[ActionDecision | ActionFeedback] = []
    errors: list[Exception] = []
    runtime = _runtime(
        tmp_path,
        source,
        model,
        commands,
        actions,
        Event(),
        finite_source=True,
        producer_full=full,
    )
    runner = _run(runtime, errors)
    try:
        source.queue.put(_final(0, "Telegram"))
        assert model.entered.wait(1)
        for segment in range(1, 8):
            source.queue.put(_final(segment))
        assert full.wait(1)
        runtime.stop()
        assert source.stopped.is_set()
    finally:
        model.release.set()
        source.queue.put(None)
        runner.join(3)
    assert not runner.is_alive()
    assert errors == []
    assert commands == []
    assert actions == []
    assert len(model.calls) == 1


def test_stop_during_eof_drain_reports_still_running_model(tmp_path: Path) -> None:
    model, source = BlockingModel(), Source()
    commands: list[CommandEvent] = []
    actions: list[ActionDecision | ActionFeedback] = []
    errors: list[Exception] = []
    runtime = _runtime(tmp_path, source, model, commands, actions, Event())
    runner = _run(runtime, errors)
    try:
        source.queue.put(_final(0, "Telegram"))
        assert model.entered.wait(1)
        source.queue.put(None)
        runtime.stop()
        runner.join(2)
        assert not runner.is_alive(), "stop kept the long EOF drain timeout"
        assert len(errors) == 1
        assert "in-flight inference may still be running" in str(errors[0])
        understanding = runtime._understanding
        assert understanding is not None
        assert understanding._thread is not None and understanding._thread.is_alive()
        assert commands == []
        assert actions == []
    finally:
        model.release.set()
        source.queue.put(None)
        runner.join(3)
        assert runtime._understanding is not None
        runtime._understanding.close(drain=False, timeout_s=2)
    assert runtime._understanding._thread is not None
    assert not runtime._understanding._thread.is_alive()
    assert commands == []
    assert actions == []


def test_finite_normal_eof_preserves_all_accepted_finals(tmp_path: Path) -> None:
    model, source = BlockingModel(), Source()
    commands: list[CommandEvent] = []
    actions: list[ActionDecision | ActionFeedback] = []
    errors: list[Exception] = []
    runtime = _runtime(
        tmp_path,
        source,
        model,
        commands,
        actions,
        Event(),
        finite_source=True,
    )
    runner = _run(runtime, errors)
    try:
        source.queue.put(_final(0, "Telegram"))
        assert model.entered.wait(1)
        for segment in range(1, 8):
            source.queue.put(_final(segment))
        source.queue.put(SpeechSessionEnded(0, None))
    finally:
        model.release.set()
        source.queue.put(None)
        runner.join(3)
    assert not runner.is_alive()
    assert errors == []
    assert [
        item.segment_id for item in commands if isinstance(item, CommandResolution)
    ] == list(range(8))
    assert not any(isinstance(item, ResponseRequest) for item in commands)
    assert [
        item.key.segment_id for item in actions if isinstance(item, ActionRequest)
    ] == list(range(8))
    assert len(model.calls) == 8
