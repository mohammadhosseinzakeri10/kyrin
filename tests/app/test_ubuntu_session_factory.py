"""The Ubuntu composition honors saved choices without real audio or actions."""

from dataclasses import replace
from pathlib import Path
from threading import Event

import pytest

from kyrin.actions.models import (
    ActionFeedback,
    ActionOutcome,
    ActionRequest,
    ActionResult,
)
from kyrin.app.platforms import ubuntu
from kyrin.app.settings import AllowedApp, AppSettings, SttSelection
from kyrin.audio.audio_format import AudioFormat, AudioSampleFormat
from kyrin.audio.microphone.devices import MicrophoneConfiguration
from kyrin.audio.microphone.errors import MicrophoneError
from kyrin.desktop.platforms.xdg import XdgDesktopAppCatalog
from kyrin.stt.capabilities import SpeechToTextCapabilities
from kyrin.stt.device import ComputeDevice, DevicePreference
from kyrin.stt.errors import DeviceUnavailableError
from kyrin.stt.transcript import TranscriptStatus, TranscriptUpdate


class FakeMicrophones:
    def __init__(self) -> None:
        self.keys: list[str | None] = []
        self.missing = False

    def list_inputs(self) -> tuple[()]:
        return ()

    def resolve(self, key: str | None) -> MicrophoneConfiguration:
        self.keys.append(key)
        if self.missing:
            raise MicrophoneError("selected microphone is not available")
        return MicrophoneConfiguration(
            3, AudioFormat(16000, 1, AudioSampleFormat.INT16), 320
        )


class FakeEngine:
    def __init__(self) -> None:
        self.closed = False
        self.capabilities = SpeechToTextCapabilities(
            frozenset({ComputeDevice.CPU}), frozenset({"en"}), True, False
        )

    def close(self) -> None:
        self.closed = True


class FakeSpeechController:
    """Supply final transcripts at the speech boundary, without PortAudio."""

    def __init__(self, factory: object) -> None:
        self.factory = factory

    def events(self):  # type: ignore[no-untyped-def]
        yield TranscriptUpdate(0, "Open Telegram", TranscriptStatus.FINAL, "en")
        yield TranscriptUpdate(1, "Open Browser", TranscriptStatus.FINAL, "en")

    def stop(self) -> None:
        pass


class RecordingExecutor:
    def __init__(self) -> None:
        self.requests: list[ActionRequest] = []

    def execute(self, request: ActionRequest) -> ActionResult:
        self.requests.append(request)
        return ActionResult(request.key, ActionOutcome.LAUNCH_ACCEPTED)


def _catalog(tmp_path: Path) -> XdgDesktopAppCatalog:
    directory = tmp_path / "data/applications"
    directory.mkdir(parents=True)
    for name in ("Telegram", "Browser"):
        (directory / f"{name.lower()}.desktop").write_text(
            f"[Desktop Entry]\nType=Application\nName={name}\nExec=true\n",
            encoding="utf-8",
        )
    return XdgDesktopAppCatalog((tmp_path / "data",))


def _settings(tmp_path: Path, **changes: object) -> AppSettings:
    base = AppSettings(
        microphone_device_key='["PulseAudio","USB Mic"]',
        stt=SttSelection("fake", tmp_path / "model", "en"),
        allowed_apps=(AllowedApp("telegram", "telegram.desktop"),),
    )
    return replace(base, **changes)


def test_dry_run_allows_only_configured_app_without_executing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(ubuntu, "SpeechSessionController", FakeSpeechController)
    microphones = FakeMicrophones()
    engine = FakeEngine()
    events: list[ubuntu.ApplicationEvent] = []
    executor = RecordingExecutor()
    factory = ubuntu.UbuntuSessionFactory(
        stt_openers={"fake": lambda selection: engine},
        on_event=events.append,
        microphones=microphones,
        catalog=_catalog(tmp_path),
        detector_factory=lambda: object(),  # unused by the fake speech controller
        executor_factory=lambda paths: executor,
    )

    with factory(_settings(tmp_path)) as runtime:
        runtime.run()

    assert engine.closed
    assert microphones.keys == ['["PulseAudio","USB Mic"]']
    assert executor.requests == []
    requests = [event for event in events if isinstance(event, ActionRequest)]
    assert [item.intent.target for item in requests] == ["telegram"]


def test_enabled_actions_use_only_exact_registered_allowlist(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    action_completed = Event()

    class WaitingSpeechController(FakeSpeechController):
        def events(self):  # type: ignore[no-untyped-def]
            yield TranscriptUpdate(0, "Open Telegram", TranscriptStatus.FINAL, "en")
            assert action_completed.wait(1)
            yield TranscriptUpdate(1, "Open Browser", TranscriptStatus.FINAL, "en")

    monkeypatch.setattr(ubuntu, "SpeechSessionController", WaitingSpeechController)
    paths_seen: list[dict[str, Path]] = []
    executor = RecordingExecutor()
    events: list[ubuntu.ApplicationEvent] = []

    def on_event(event: ubuntu.ApplicationEvent) -> None:
        events.append(event)
        if isinstance(event, ActionFeedback):
            action_completed.set()

    def make_executor(paths):  # type: ignore[no-untyped-def]
        paths_seen.append(dict(paths))
        return executor

    factory = ubuntu.UbuntuSessionFactory(
        stt_openers={"fake": lambda selection: FakeEngine()},
        on_event=on_event,
        microphones=FakeMicrophones(),
        catalog=_catalog(tmp_path),
        detector_factory=lambda: object(),
        executor_factory=make_executor,
    )
    settings = _settings(tmp_path, action_execution_enabled=True)

    with factory(settings) as runtime:
        runtime.run()

    assert paths_seen == [{"telegram": tmp_path / "data/applications/telegram.desktop"}]
    assert [request.intent.target for request in executor.requests] == ["telegram"]
    assert any(isinstance(event, ActionFeedback) for event in events)


def test_missing_microphone_and_explicit_gpu_fail_without_capture(
    tmp_path: Path,
) -> None:
    microphones = FakeMicrophones()
    engine = FakeEngine()
    opened: list[SttSelection] = []

    def open_engine(selection: SttSelection) -> FakeEngine:
        opened.append(selection)
        return engine

    factory = ubuntu.UbuntuSessionFactory(
        stt_openers={"fake": open_engine},
        on_event=lambda event: None,
        microphones=microphones,
        catalog=_catalog(tmp_path),
        detector_factory=lambda: object(),
    )
    microphones.missing = True
    with pytest.raises(MicrophoneError, match="not available"):
        with factory(_settings(tmp_path)):
            pass
    assert opened == []

    microphones.missing = False
    gpu = _settings(
        tmp_path,
        stt=SttSelection("fake", tmp_path / "model", "en", DevicePreference.GPU),
    )
    with pytest.raises(DeviceUnavailableError, match="cannot run on GPU"):
        with factory(gpu):
            pass
    assert engine.closed


def test_unknown_backend_fails_before_touching_microphone(tmp_path: Path) -> None:
    microphones = FakeMicrophones()
    factory = ubuntu.UbuntuSessionFactory(
        stt_openers={},
        on_event=lambda event: None,
        microphones=microphones,
        catalog=_catalog(tmp_path),
    )
    with pytest.raises(ValueError, match="not installed"):
        with factory(_settings(tmp_path)):
            pass
    assert microphones.keys == []
