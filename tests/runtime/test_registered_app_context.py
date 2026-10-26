"""An allowed installed app supplies its spoken name to the live runtime."""

from collections.abc import Callable, Generator
from pathlib import Path
from runpy import run_path
from threading import Event

import pytest

from kyrin.actions.models import ActionOutcome, ActionRequest, ActionResult
from kyrin.runtime.speech_sessions import SpeechSessionEnded
from kyrin.stt.transcript import TranscriptStatus, TranscriptUpdate

SCRIPT = Path(__file__).resolve().parents[2] / "scripts/audio/check_live_speech.py"
NAMESPACE = run_path(str(SCRIPT))
parse_args = NAMESPACE["parse_args"]
run = NAMESPACE["run"]


def test_registered_launch_app_name_works_without_second_spoken_binding(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    app_dir = tmp_path / "applications"
    app_dir.mkdir()
    entry = app_dir / "chat.desktop"
    entry.write_text(
        "[Desktop Entry]\nType=Application\nName=Orbit Notes\n", encoding="utf-8"
    )
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    monkeypatch.setenv("XDG_DATA_DIRS", str(tmp_path))
    completed = Event()
    calls: list[ActionRequest] = []

    class FakeEngine:
        def __init__(self, *args: object, **kwargs: object) -> None:
            pass

        def close(self) -> None:
            pass

    class FakeController:
        def __init__(self, factory: Callable[..., object], policy: object) -> None:
            pass

        def events(self) -> Generator[TranscriptUpdate | SpeechSessionEnded]:
            yield TranscriptUpdate(0, "Open Orbit Notes", TranscriptStatus.FINAL, "en")
            assert completed.wait(2), "the registered app was not dispatched"

        def stop(self) -> None:
            pass

    class FakeExecutor:
        def __init__(self, apps: object) -> None:
            pass

        def execute(self, request: ActionRequest) -> ActionResult:
            calls.append(request)
            completed.set()
            return ActionResult(request.key, ActionOutcome.LAUNCH_ACCEPTED)

    globals_ = run.__globals__
    monkeypatch.setitem(globals_, "SileroVad", lambda: object())
    monkeypatch.setitem(globals_, "WhisperEngine", FakeEngine)
    monkeypatch.setitem(globals_, "SpeechSessionController", FakeController)
    monkeypatch.setitem(globals_, "LinuxDesktopEntryExecutor", FakeExecutor)

    run(
        parse_args(
            [
                "--mode",
                "commands",
                "--until-stopped",
                "--stt-backend",
                "whisper",
                "--model-path",
                "/unused/model.bin",
                "--whisper-server",
                "/unused/whisper-server",
                "--language",
                "en",
                "--no-voice-responses",
                "--execute-actions",
                "--launch-app",
                f"chat={entry}",
            ]
        )
    )

    assert len(calls) == 1
    assert calls[0].intent.target == "chat"


def test_conflicting_registered_bindings_fail_before_opening_microphone(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    app_dir = tmp_path / "applications"
    app_dir.mkdir()
    entry = app_dir / "notes.desktop"
    entry.write_text(
        "[Desktop Entry]\nType=Application\nName=Notes\n", encoding="utf-8"
    )
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    monkeypatch.setenv("XDG_DATA_DIRS", str(tmp_path))
    monkeypatch.setitem(run.__globals__, "SileroVad", lambda: object())

    with pytest.raises(ValueError, match="bindings disagree"):
        run(
            parse_args(
                [
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
                    "--execute-actions",
                    "--launch-app",
                    f"notes={entry}",
                    "--spoken-app-binding",
                    "notes.desktop=other",
                ]
            )
        )
