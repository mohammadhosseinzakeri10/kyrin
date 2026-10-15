"""Offline voice output follows the response channel without blocking capture."""

import subprocess
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


def test_preview_speaks_with_its_own_selection_without_changing_normal_voice() -> None:
    backend = BlockingSynthesizer()
    speaker = ResponseSpeaker(backend, on_error=lambda exc: None, tail_s=0)
    response = PresentedResponse(
        0, 1, "Preview", ResponseChannel.TEXT_AND_VOICE, "en"
    )
    preview_calls: list[tuple[str, str]] = []
    try:
        assert speaker.submit(
            response,
            speak=lambda text, language: preview_calls.append((text, language)),
        )
        assert speaker.wait_until_idle(2)
        assert preview_calls == [("Preview", "en")]
        assert backend.calls == []
    finally:
        speaker.close()


def test_local_backend_waits_for_offline_speech_and_propagates_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[list[str]] = []

    def fake_run(
        command: list[str], **kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(subprocess, "run", fake_run)
    backend = SpeechDispatcherSynthesizer("/usr/bin/spd-say")
    backend.speak("متوجه نشدم.", "fa-IR")
    assert calls[0][-2:] == ["fa", "متوجه نشدم."]
    assert "--wait" in calls[0]
    assert calls[0][calls[0].index("--output-module") + 1] == "espeak-ng"

    def failing_run(
        command: list[str], **kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(command, 1, "", "unavailable")

    monkeypatch.setattr(subprocess, "run", failing_run)
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
