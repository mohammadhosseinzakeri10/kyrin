"""Offline voice output follows the response channel without blocking capture."""

from collections.abc import Callable
from pathlib import Path
from runpy import run_path
from threading import Event

import pytest

from kyrin.commands.coordinator import CommandCoordinator
from kyrin.commands.demo_interpreter import DemoCommandInterpreter
from kyrin.commands.models import ResponseChannel
from kyrin.responses.presenter import PresentedResponse, ResponsePresenter
from kyrin.responses.speech import (
    ResponseSpeaker,
    SpeechDispatcherSynthesizer,
    SpeechSynthesisError,
)
from kyrin.stt.transcript import TranscriptStatus, TranscriptUpdate


class BlockingSynthesizer:
    def __init__(self) -> None:
        self.started = Event()
        self.release = Event()
        self.calls: list[tuple[str, str]] = []

    def speak(self, text: str, language: str) -> None:
        self.calls.append((text, language))
        self.started.set()
        assert self.release.wait(2)


def test_voice_is_async_and_suppresses_capture_until_playback_finishes() -> None:
    backend = BlockingSynthesizer()
    errors: list[SpeechSynthesisError] = []
    speaker = ResponseSpeaker(backend, on_error=errors.append, tail_s=0)
    response = PresentedResponse(
        0, 1, "Please repeat.", ResponseChannel.TEXT_AND_VOICE, "en"
    )
    try:
        assert speaker.submit(response)
        assert speaker.is_active
        assert not speaker.wait_until_idle(0)
        assert backend.started.wait(2)
        assert backend.calls == [("Please repeat.", "en")]
        assert speaker.submit(
            PresentedResponse(0, 2, "Text only", ResponseChannel.TEXT_ONLY, "en")
        )
    finally:
        backend.release.set()
        assert speaker.wait_until_idle(2)
        speaker.close()
    assert not speaker.is_active
    assert not errors


def test_stale_queued_prompt_is_not_spoken_after_stage_changes() -> None:
    backend = BlockingSynthesizer()
    speaker = ResponseSpeaker(backend, on_error=lambda exc: None, tail_s=0)
    current = True
    first = PresentedResponse(
        None, None, "First stage", ResponseChannel.TEXT_AND_VOICE, "en"
    )
    second = PresentedResponse(
        None, None, "Second stage", ResponseChannel.TEXT_AND_VOICE, "en"
    )
    try:
        assert speaker.submit(first)
        assert backend.started.wait(2)
        assert speaker.submit(second, still_current=lambda: current)
        current = False
        backend.release.set()
        assert speaker.wait_until_idle(2)
        assert backend.calls == [("First stage", "en")]
    finally:
        backend.release.set()
        speaker.close()


def test_replacing_prompt_interrupts_old_voice_and_starts_new_one() -> None:
    class InterruptibleSynthesizer:
        def __init__(self) -> None:
            self.started = Event()
            self.interrupted = Event()
            self.calls: list[str] = []

        def speak(self, text: str, language: str) -> None:
            self.calls.append(text)
            if text == "First":
                self.started.set()
                assert self.interrupted.wait(2)

        def interrupt(self) -> None:
            self.interrupted.set()

    backend = InterruptibleSynthesizer()
    speaker = ResponseSpeaker(backend, on_error=lambda exc: None, tail_s=0)
    first = PresentedResponse(None, None, "First", ResponseChannel.TEXT_AND_VOICE, "en")
    second = PresentedResponse(
        None, None, "Second", ResponseChannel.TEXT_AND_VOICE, "en"
    )
    try:
        assert speaker.replace(first)
        assert backend.started.wait(2)
        assert speaker.replace(second)
        assert speaker.wait_until_idle(2)
        assert backend.calls == ["First", "Second"]
    finally:
        speaker.close()


def test_disabling_voice_interrupts_playback_and_ignores_later_speech() -> None:
    class InterruptibleSynthesizer:
        def __init__(self) -> None:
            self.started = Event()
            self.interrupted = Event()
            self.calls: list[str] = []

        def speak(self, text: str, language: str) -> None:
            self.calls.append(text)
            self.started.set()
            assert self.interrupted.wait(2)

        def interrupt(self) -> None:
            self.interrupted.set()

    backend = InterruptibleSynthesizer()
    speaker = ResponseSpeaker(backend, on_error=lambda exc: None, tail_s=0)
    response = PresentedResponse(
        None, None, "Prompt", ResponseChannel.TEXT_AND_VOICE, "en"
    )
    try:
        assert speaker.submit(response)
        assert backend.started.wait(2)
        speaker.set_enabled(False)
        assert speaker.wait_until_idle(2)
        assert speaker.submit(response)
        assert speaker.replace(response)
        assert backend.calls == ["Prompt"]
    finally:
        speaker.close()


def test_preview_speaks_with_its_own_selection_without_changing_normal_voice() -> None:
    backend = BlockingSynthesizer()
    speaker = ResponseSpeaker(backend, on_error=lambda exc: None, tail_s=0)
    response = PresentedResponse(0, 1, "Preview", ResponseChannel.TEXT_AND_VOICE, "en")
    preview_calls: list[tuple[str, str]] = []
    try:
        assert speaker.submit(
            response,
            speak=lambda text, language, valid: (
                preview_calls.append((text, language)) if valid() else None
            ),
        )
        assert speaker.wait_until_idle(2)
        assert preview_calls == [("Preview", "en")]
        assert backend.calls == []
    finally:
        speaker.close()


def test_local_backend_waits_for_offline_speech_and_propagates_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from kyrin.responses import speech

    calls: list[tuple[str, str, int, str]] = []
    closed: list[bool] = []

    class Connection:
        output_uncertain = False

        def __init__(self, timeout_s: float) -> None:
            assert timeout_s == 15

        def speak(
            self,
            text: str,
            language: str,
            rate: int,
            voice: str,
            cancelled: Event,
            valid: Callable[[], bool],
            playing: Callable[[bool], None],
        ) -> None:
            assert valid()
            calls.append((text, language, rate, voice))
            playing(True)
            assert backend.is_playing
            playing(False)

        def close(self) -> None:
            closed.append(True)

    monkeypatch.setattr(speech, "LocalSpeechConnection", Connection)
    backend = SpeechDispatcherSynthesizer("/usr/bin/spd-say")
    backend.speak("متوجه نشدم.", "fa-IR")
    assert calls == [("متوجه نشدم.", "fa", 0, "default")]
    assert closed == [True]
    assert not backend.is_playing
    assert backend.last_playback_end > 0

    def unavailable(timeout_s: float) -> None:
        raise PermissionError("unavailable")

    monkeypatch.setattr(speech, "LocalSpeechConnection", unavailable)
    with pytest.raises(SpeechSynthesisError):
        backend.speak("Please repeat.", "en")


def test_unclear_final_command_is_displayed_without_voice(
    capsys: pytest.CaptureFixture[str],
) -> None:
    script = Path(__file__).resolve().parents[2] / "scripts/audio/check_live_speech.py"
    print_command_event = run_path(str(script))["print_command_event"]
    backend = BlockingSynthesizer()
    speaker = ResponseSpeaker(backend, on_error=lambda exc: None, tail_s=0)
    coordinator = CommandCoordinator(DemoCommandInterpreter())
    decisions = coordinator.observe(
        TranscriptUpdate(0, "to open telegram", TranscriptStatus.FINAL, "en")
    )
    try:
        for decision in decisions:
            print_command_event(decision, 0, ResponsePresenter("en"), speaker)
        assert not backend.started.wait(0.05)
        assert backend.calls == []
        assert "Please repeat the command." in capsys.readouterr().out
    finally:
        backend.release.set()
        speaker.close()


def test_queue_and_synthesis_do_not_mask_input_but_playback_does() -> None:
    class Generating(BlockingSynthesizer):
        is_playing = False
        last_playback_end = 0.0

    backend = Generating()
    speaker = ResponseSpeaker(backend, on_error=lambda exc: None, tail_s=0)
    response = PresentedResponse(
        None, None, "Hello", ResponseChannel.TEXT_AND_VOICE, "en"
    )
    try:
        assert speaker.submit(response)
        assert backend.started.wait(2)
        assert speaker.is_active
        assert not speaker.is_playing
        assert speaker.submit(response)
        backend.is_playing = True
        assert speaker.is_playing
        backend.is_playing = False
        assert not speaker.is_playing
        speaker.interrupt()
        backend.release.set()
        assert speaker.wait_until_idle(2)
        assert backend.calls == [("Hello", "en")]
    finally:
        backend.release.set()
        speaker.close()


def test_interrupt_clears_full_queue_and_rejects_late_custom_synthesis() -> None:
    backend = BlockingSynthesizer()
    entered, release = Event(), Event()
    heard: list[str] = []
    response = PresentedResponse(
        None, None, "old", ResponseChannel.TEXT_AND_VOICE, "en"
    )

    def custom(text: str, language: str, valid: Callable[[], bool]) -> None:
        entered.set()
        assert release.wait(2)
        if valid():
            heard.append(text)

    speaker = ResponseSpeaker(
        backend, on_error=lambda exc: None, max_pending=1, tail_s=0
    )
    try:
        assert speaker.submit(response, speak=custom)
        assert entered.wait(2)
        assert speaker.submit(response)
        assert not speaker.submit(response)
        speaker.interrupt()
        release.set()
        assert speaker.wait_until_idle(2)
        assert heard == []
        assert backend.calls == []
    finally:
        release.set()
        speaker.close()
