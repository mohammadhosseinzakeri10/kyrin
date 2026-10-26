"""An opt-in command diagnostic can listen until a manual, clean stop."""

from collections.abc import Callable, Iterator
from pathlib import Path
from runpy import run_path
from threading import Event

import pytest

from kyrin.actions.models import ActionRequest
from kyrin.stt.device import ComputeDevice
from kyrin.stt.transcript import TranscriptStatus, TranscriptUpdate

SCRIPT = Path(__file__).resolve().parents[2] / "scripts/audio/check_live_speech.py"
NAMESPACE = run_path(str(SCRIPT))
parse_args = NAMESPACE["parse_args"]
run = NAMESPACE["run"]


def _base_args() -> list[str]:
    return [
        "--mode",
        "commands",
        "--stt-backend",
        "whisper",
        "--model-path",
        "/unused/model.bin",
        "--whisper-server",
        "/unused/whisper-server",
        "--language",
        "en",
        "--no-voice-responses",
    ]


def test_long_listening_is_explicit_and_keeps_the_short_default() -> None:
    assert parse_args(_base_args()).seconds == 10.0
    long_run = parse_args([*_base_args(), "--until-stopped"])
    assert long_run.until_stopped
    assert long_run.seconds is None
    assert parse_args([*_base_args(), "--seconds", "120"]).seconds == 120.0

    with pytest.raises(SystemExit):
        parse_args([*_base_args(), "--seconds", "10", "--until-stopped"])
    with pytest.raises(SystemExit):
        parse_args([*_base_args(), "--seconds", "121"])
    with pytest.raises(SystemExit):
        parse_args([*_base_args(), "--mode", "stt", "--until-stopped"])
    assert parse_args(_base_args()).compute_device == "cpu"
    assert (
        parse_args([*_base_args(), "--compute-device", "gpu"]).compute_device == "gpu"
    )
    with pytest.raises(SystemExit):
        parse_args([*_base_args(), "--stt-backend", "vosk", "--compute-device", "gpu"])


def test_vocabulary_hints_are_explicit_and_bounded() -> None:
    args = parse_args([*_base_args(), "--vocabulary-hint", "مرورگر"])
    assert args.stt_options.vocabulary_hints == ("مرورگر",)
    assert parse_args(_base_args()).stt_options.vocabulary_hints == ()
    with pytest.raises(SystemExit):
        parse_args([*_base_args(), "--vocabulary-hint", " "])
    with pytest.raises(SystemExit):
        parse_args(
            [
                *_base_args(),
                "--stt-backend",
                "vosk",
                "--vocabulary-hint",
                "مرورگر",
            ]
        )


def test_manual_stop_closes_controller_and_engine_without_a_timer(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    runtime_globals = run.__globals__
    completed = Event()
    printed = 0
    print_action = runtime_globals["print_action_decision"]

    def show_action(*args: object, **kwargs: object) -> None:
        nonlocal printed
        print_action(*args, **kwargs)
        if isinstance(args[0], ActionRequest):
            printed += 1
            if printed == 2:
                completed.set()

    monkeypatch.setitem(runtime_globals, "print_action_decision", show_action)

    class FakeEngine:
        def __init__(self, *args: object, **kwargs: object) -> None:
            self.closed = False
            self.compute_device = kwargs["compute_device"]
            engines.append(self)

        def close(self) -> None:
            self.closed = True

    class FakeController:
        def __init__(self, factory: Callable[..., object], policy: object) -> None:
            self.stopped = False
            controllers.append(self)

        def events(self) -> Iterator[TranscriptUpdate]:
            yield TranscriptUpdate(0, "Open Telegram", TranscriptStatus.FINAL, "en")
            yield TranscriptUpdate(1, "Open browser", TranscriptStatus.FINAL, "en")
            assert completed.wait(2), "ordered command outputs did not finish"
            raise KeyboardInterrupt

        def stop(self) -> None:
            self.stopped = True

    engines: list[FakeEngine] = []
    controllers: list[FakeController] = []

    def forbidden_timer(*args: object, **kwargs: object) -> None:
        raise AssertionError("unbounded listening must not create a timer")

    monkeypatch.setitem(runtime_globals, "SileroVad", lambda: object())
    monkeypatch.setitem(runtime_globals, "WhisperEngine", FakeEngine)
    monkeypatch.setitem(runtime_globals, "SpeechSessionController", FakeController)
    monkeypatch.setitem(runtime_globals, "Timer", forbidden_timer)

    run(parse_args([*_base_args(), "--until-stopped", "--compute-device", "gpu"]))

    output = capsys.readouterr().out
    assert output.count("authorized dry-run request") == 2
    assert "Listening stopped by user." in output
    assert len(controllers) == len(engines) == 1
    assert controllers[0].stopped
    assert engines[0].closed
    assert engines[0].compute_device is ComputeDevice.GPU
