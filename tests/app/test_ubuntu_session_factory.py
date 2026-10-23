"""The Ubuntu composition honors saved choices without real audio or actions."""

from dataclasses import replace
from pathlib import Path
from threading import Event
from typing import cast

import pytest

from kyrin.actions.models import (
    ActionFeedback,
    ActionOutcome,
    ActionRequest,
    ActionResult,
)
from kyrin.app.platforms import ubuntu
from kyrin.app.settings import (
    AllowedApp,
    AppSettings,
    AppSpokenAliases,
    CommandModelSelection,
    SttSelection,
)
from kyrin.audio.audio_format import AudioFormat, AudioSampleFormat
from kyrin.audio.file_input import FILE_AUDIO_FORMAT, AudioFileInput
from kyrin.audio.microphone.devices import MicrophoneConfiguration
from kyrin.audio.microphone.errors import MicrophoneError
from kyrin.commands.models import CommandKind, ResponseKind, ResponseRequest
from kyrin.commands.understanding import (
    MeaningStep,
    ProposedMeaning,
    RequestedOperation,
    UnderstandingResult,
    UnderstandingStatus,
)
from kyrin.desktop.app_activation import ActivationAttempt
from kyrin.desktop.platforms.xdg import XdgDesktopAppCatalog
from kyrin.desktop.window_presence import WindowPresence
from kyrin.memory.history import SqliteConversationHistory
from kyrin.responses.visual_status import VisualPresentation, VisualStatus
from kyrin.runtime.command_runtime import LiveCommandRuntime
from kyrin.stt.capabilities import SpeechToTextCapabilities
from kyrin.stt.device import ComputeDevice, DevicePreference
from kyrin.stt.errors import DeviceUnavailableError, SpeechToTextError
from kyrin.stt.transcript import TranscriptStatus, TranscriptUpdate
from kyrin.system_power.flow import (
    InertPowerBackend,
    PowerAction,
    PowerStage,
    SystemPowerFlow,
)


@pytest.fixture(autouse=True)
def isolate_conversation_history(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Fake live sessions must never write into the user's XDG data store."""
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg-data"))


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


def test_whisper_openers_select_device_before_starting_server(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    opened: list[tuple[Path, ComputeDevice]] = []
    cpu = tmp_path / "cpu-server"
    gpu = tmp_path / "gpu-server"

    def fake_engine(
        path: Path, model: Path, *, language: str, compute_device: ComputeDevice
    ) -> FakeEngine:
        assert model == tmp_path / "model"
        assert language == "en"
        opened.append((path, compute_device))
        return FakeEngine()

    monkeypatch.setattr(ubuntu, "WhisperEngine", fake_engine)
    opener = ubuntu.standard_stt_openers(
        whisper_server_path=cpu, whisper_gpu_server_path=gpu
    )["whisper"]
    for preference in (
        DevicePreference.CPU,
        DevicePreference.GPU,
        DevicePreference.AUTO,
    ):
        opener(SttSelection("whisper", tmp_path / "model", "en", preference))
    assert opened == [
        (cpu, ComputeDevice.CPU),
        (gpu, ComputeDevice.GPU),
        (gpu, ComputeDevice.GPU),
    ]


def test_whisper_auto_falls_back_but_explicit_gpu_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    opened: list[ComputeDevice] = []

    def fake_engine(
        path: Path, model: Path, *, language: str, compute_device: ComputeDevice
    ) -> FakeEngine:
        opened.append(compute_device)
        if compute_device is ComputeDevice.GPU:
            raise SpeechToTextError("GPU process failed")
        return FakeEngine()

    monkeypatch.setattr(ubuntu, "WhisperEngine", fake_engine)
    opener = ubuntu.standard_stt_openers(
        whisper_server_path=tmp_path / "cpu",
        whisper_gpu_server_path=tmp_path / "gpu",
    )["whisper"]
    opener(SttSelection("whisper", tmp_path / "model", "en"))
    assert opened == [ComputeDevice.GPU, ComputeDevice.CPU]
    with pytest.raises(DeviceUnavailableError, match="GPU runtime"):
        opener(SttSelection("whisper", tmp_path / "model", "en", DevicePreference.GPU))


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


def test_power_reply_during_voice_playback_is_accepted_with_echo_cancellation(
    tmp_path: Path,
) -> None:
    class BusySpeaker:
        def __init__(self) -> None:
            self.is_active = True

    class ReadyEchoCancellation:
        closed = False

        def start(self) -> bool:
            return True

        def close(self) -> None:
            self.closed = True

    prompts = []
    flow = SystemPowerFlow(InertPowerBackend(), prompts.append, enabled=True)
    echo = ReadyEchoCancellation()
    speaker = BusySpeaker()
    factory = ubuntu.UbuntuSessionFactory(
        stt_openers={"fake": lambda selection: FakeEngine()},
        on_event=lambda event: None,
        microphones=FakeMicrophones(),
        catalog=_catalog(tmp_path),
        detector_factory=lambda: object(),
        response_speaker=cast(ubuntu.ResponseSpeaker, speaker),
        system_power=flow,
        echo_cancellation_factory=lambda: cast(ubuntu.PipeWireEchoCancellation, echo),
    )
    settings = _settings(
        tmp_path,
        microphone_device_key=None,
        action_execution_enabled=True,
        system_power_enabled=True,
    )
    with factory(settings):
        assert flow.start(PowerAction.RESTART)
        for _ in range(100):
            if any(prompt.stage is PowerStage.FIRST for prompt in prompts):
                break
            Event().wait(0.01)
        assert flow.on_final_speech("Yes")
        assert any(prompt.stage is PowerStage.SECOND for prompt in prompts)
    assert echo.closed


def test_cleanup_closes_stt_even_if_echo_cancellation_close_fails(
    tmp_path: Path,
) -> None:
    class FaultyEchoCancellation:
        def start(self) -> bool:
            return True

        def close(self) -> None:
            raise RuntimeError("echo cleanup failed")

    engine = FakeEngine()
    factory = ubuntu.UbuntuSessionFactory(
        stt_openers={"fake": lambda selection: engine},
        on_event=lambda event: None,
        microphones=FakeMicrophones(),
        catalog=_catalog(tmp_path),
        detector_factory=lambda: object(),
        response_speaker=cast(ubuntu.ResponseSpeaker, object()),
        echo_cancellation_factory=lambda: cast(
            ubuntu.PipeWireEchoCancellation, FaultyEchoCancellation()
        ),
    )
    settings = _settings(tmp_path, microphone_device_key=None)

    with pytest.raises(RuntimeError, match="echo cleanup failed"):
        with factory(settings):
            pass

    assert engine.closed


def test_failed_capture_stop_cancels_owned_inference_without_closing_active_engine(
    tmp_path: Path,
) -> None:
    class CancellableEngine(FakeEngine):
        cancelled = False

        def cancel_pending_inference(self) -> None:
            self.cancelled = True

    engine = CancellableEngine()
    factory = ubuntu.UbuntuSessionFactory(
        stt_openers={"fake": lambda selection: engine},
        on_event=lambda event: None,
        microphones=FakeMicrophones(),
        catalog=_catalog(tmp_path),
        detector_factory=lambda: object(),
    )

    with pytest.raises(ubuntu.AudioCaptureStopError):
        with factory(_settings(tmp_path)):
            raise ubuntu.AudioCaptureStopError("session still active")

    assert engine.cancelled
    assert not engine.closed


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
    history_path = ubuntu.default_history_path()
    assert history_path == tmp_path / "xdg-data/kyrin/memory/conversation.sqlite3"
    history = SqliteConversationHistory(history_path)
    try:
        assert [turn.text for turn in history.recent()] == [
            "Open Telegram",
            "Open Browser",
        ]
    finally:
        history.close()


def test_audio_file_session_uses_file_without_resolving_microphone(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class FileSpeechController:
        def __init__(self, create_pipeline):  # type: ignore[no-untyped-def]
            self.create_pipeline = create_pipeline

        def events(self):  # type: ignore[no-untyped-def]
            self.create_pipeline()
            yield TranscriptUpdate(0, "Open Telegram", TranscriptStatus.FINAL, "en")

        def stop(self) -> None:
            pass

    sources: list[object] = []

    def capture_pipeline(source, detector, engine, **kwargs):  # type: ignore[no-untyped-def]
        sources.append(source)
        assert source.audio_format == FILE_AUDIO_FORMAT
        assert kwargs["options"].emit_partials is False
        return object()

    monkeypatch.setattr(ubuntu, "SpeechSessionController", FileSpeechController)
    monkeypatch.setattr(ubuntu, "FileSpeechPipeline", capture_pipeline)
    microphones = FakeMicrophones()
    microphones.missing = True
    audio_file = tmp_path / "speech.wav"
    audio_file.write_bytes(b"RIFF")
    factory = ubuntu.UbuntuSessionFactory(
        stt_openers={"fake": lambda selection: FakeEngine()},
        on_event=lambda event: None,
        microphones=microphones,
        catalog=_catalog(tmp_path),
        detector_factory=lambda: object(),
    )
    with factory.for_audio_file(audio_file)(_settings(tmp_path)) as runtime:
        runtime.run()
    assert microphones.keys == []
    assert len(sources) == 1
    assert isinstance(sources[0], AudioFileInput)


def test_scroll_reaches_unselected_focused_app_without_window_controls(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    completed = Event()
    requested: list[ActionRequest] = []
    observed: list[ubuntu.ApplicationEvent] = []

    class ScrollSpeechController(FakeSpeechController):
        def events(self):  # type: ignore[no-untyped-def]
            yield TranscriptUpdate(0, "Scroll down", TranscriptStatus.FINAL, "en")
            assert completed.wait(2)

    class ScrollExecutor:
        def __init__(self, delegate, **kwargs) -> None:
            assert kwargs["desktop_ids"] == {}
            assert kwargs["allow_any_focused_app"] is True

        def execute(self, request: ActionRequest) -> ActionResult:
            requested.append(request)
            return ActionResult(request.key, ActionOutcome.LAUNCH_ACCEPTED)

    def on_event(event: ubuntu.ApplicationEvent) -> None:
        observed.append(event)
        if isinstance(event, ActionFeedback):
            completed.set()

    monkeypatch.setattr(ubuntu, "SpeechSessionController", ScrollSpeechController)
    monkeypatch.setattr(ubuntu, "DesktopScrollExecutor", ScrollExecutor)
    factory = ubuntu.UbuntuSessionFactory(
        stt_openers={"fake": lambda selection: FakeEngine()},
        on_event=on_event,
        microphones=FakeMicrophones(),
        catalog=_catalog(tmp_path),
        detector_factory=lambda: object(),
        executor_factory=lambda paths: RecordingExecutor(),
        focused_window=lambda: ("unselected.desktop", 42),
    )
    settings = _settings(
        tmp_path,
        allowed_apps=(),
        allowed_window_apps=(),
        allow_desktop_scroll=True,
        action_execution_enabled=True,
    )
    with factory(settings) as runtime:
        runtime.run()

    assert [request.intent.target for request in requested] == ["unselected.desktop"]
    assert any(
        isinstance(event, ActionFeedback)
        and event.outcome is ActionOutcome.LAUNCH_ACCEPTED
        for event in observed
    )


def test_visible_click_reaches_unselected_focused_app(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    completed = Event()
    requested: list[ActionRequest] = []

    class ControlSpeechController(FakeSpeechController):
        def events(self):  # type: ignore[no-untyped-def]
            yield TranscriptUpdate(0, "Click Advanced", TranscriptStatus.FINAL, "en")
            assert completed.wait(2)

    class ControlExecutor:
        def __init__(self, delegate, **kwargs) -> None:
            assert kwargs["identity_reader"]() == ("unselected.desktop", 42)

        def execute(self, request: ActionRequest) -> ActionResult:
            requested.append(request)
            completed.set()
            return ActionResult(request.key, ActionOutcome.LAUNCH_ACCEPTED)

    monkeypatch.setattr(ubuntu, "SpeechSessionController", ControlSpeechController)
    monkeypatch.setattr(ubuntu, "DesktopControlExecutor", ControlExecutor)
    factory = ubuntu.UbuntuSessionFactory(
        stt_openers={"fake": lambda selection: FakeEngine()},
        on_event=lambda _event: None,
        microphones=FakeMicrophones(),
        catalog=_catalog(tmp_path),
        detector_factory=lambda: object(),
        executor_factory=lambda paths: RecordingExecutor(),
        focused_window=lambda: ("unselected.desktop", 42),
        chat_verifier=cast(ubuntu.ChatVerifier, object()),
    )
    settings = _settings(
        tmp_path,
        allowed_apps=(),
        allow_desktop_control=True,
        action_execution_enabled=True,
    )
    with factory(settings) as runtime:
        runtime.run()
    assert len(requested) == 1
    assert requested[0].intent.kind is CommandKind.VISIBLE_CONTROL
    assert requested[0].intent.target == "Advanced"


def test_selected_command_model_reaches_live_transcript_without_executing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class PoliteSpeechController(FakeSpeechController):
        def events(self):  # type: ignore[no-untyped-def]
            yield TranscriptUpdate(
                0, "Please open Telegram", TranscriptStatus.FINAL, "en"
            )

    class FakeServer:
        def __enter__(self) -> str:
            return "http://127.0.0.1:11435"

        def __exit__(self, *_exc: object) -> None:
            pass

    class FakeCommandModel:
        def __init__(self, endpoint: str, model: str, device: DevicePreference):
            assert endpoint == "http://127.0.0.1:11435"
            assert model == "qwen3.5:4b"
            assert device is DevicePreference.CPU

        def understand(self, source, *, context):  # type: ignore[no-untyped-def]
            assert source.text == "Please open Telegram"
            return UnderstandingResult(
                UnderstandingStatus.READY,
                (
                    ProposedMeaning(
                        (MeaningStep(RequestedOperation.OPEN_APP, "Telegram"),)
                    ),
                ),
            )

    monkeypatch.setattr(ubuntu, "SpeechSessionController", PoliteSpeechController)
    monkeypatch.setattr(ubuntu, "OllamaCommandEngine", FakeCommandModel)
    monkeypatch.setattr(ubuntu, "installed_ollama_models", lambda path: ("qwen3.5:4b",))
    events: list[ubuntu.ApplicationEvent] = []
    executor = RecordingExecutor()
    factory = ubuntu.UbuntuSessionFactory(
        stt_openers={"fake": lambda selection: FakeEngine()},
        on_event=events.append,
        microphones=FakeMicrophones(),
        catalog=_catalog(tmp_path),
        detector_factory=lambda: object(),
        executor_factory=lambda paths: executor,
        command_server_factory=lambda selection: FakeServer(),
    )
    settings = _settings(
        tmp_path,
        command_model=CommandModelSelection(
            "ollama", "qwen3.5:4b", tmp_path, DevicePreference.CPU
        ),
    )
    with factory(settings) as runtime:
        runtime.run()
    assert [
        event.intent.target for event in events if isinstance(event, ActionRequest)
    ] == ["telegram"]
    assert executor.requests == []


def test_registered_long_app_names_reach_stt_only_if_backend_supports_hints(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from kyrin.stt.device import SpeechToTextOptions

    class CaptureSpeechController(FakeSpeechController):
        def events(self):  # type: ignore[no-untyped-def]
            self.factory()
            yield TranscriptUpdate(0, "", TranscriptStatus.FINAL, "en")

    directory = tmp_path / "data/applications"
    directory.mkdir(parents=True)
    (directory / "code.desktop").write_text(
        "[Desktop Entry]\nType=Application\nName=Visual Studio Code\nExec=true\n",
        encoding="utf-8",
    )
    seen: list[SpeechToTextOptions] = []

    def pipeline(*args: object, **kwargs: object) -> object:
        options = kwargs["options"]
        assert isinstance(options, SpeechToTextOptions)
        seen.append(options)
        return object()

    monkeypatch.setattr(ubuntu, "SpeechSessionController", CaptureSpeechController)
    monkeypatch.setattr(ubuntu, "LiveSpeechPipeline", pipeline)
    settings = _settings(
        tmp_path,
        allowed_apps=(AllowedApp("visual-studio-code", "code.desktop"),),
    )
    for supported in (True, False):
        engine = FakeEngine()
        engine.capabilities = SpeechToTextCapabilities(
            frozenset({ComputeDevice.CPU}),
            frozenset({"en"}),
            True,
            False,
            supports_vocabulary_hints=supported,
        )
        factory = ubuntu.UbuntuSessionFactory(
            stt_openers={"fake": lambda selection, current=engine: current},
            on_event=lambda event: None,
            microphones=FakeMicrophones(),
            source_factory=lambda config: object(),
            catalog=XdgDesktopAppCatalog((tmp_path / "data",)),
            detector_factory=lambda: object(),
        )
        with factory(settings) as runtime:
            runtime.run()
    assert seen[0].vocabulary_hints == ("Visual Studio Code", "VS Code")
    assert seen[1].vocabulary_hints == ()


def test_omnilingual_uses_longer_pause_without_changing_other_engines(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class CaptureSpeechController(FakeSpeechController):
        def events(self):  # type: ignore[no-untyped-def]
            self.factory()
            yield TranscriptUpdate(0, "", TranscriptStatus.FINAL, "en")

    pauses: list[int] = []

    def pipeline(*args: object, **kwargs: object) -> object:
        pause = kwargs["pause_confirm_ms"]
        assert isinstance(pause, int)
        pauses.append(pause)
        return object()

    monkeypatch.setattr(ubuntu, "SpeechSessionController", CaptureSpeechController)
    monkeypatch.setattr(ubuntu, "LiveSpeechPipeline", pipeline)
    catalog = _catalog(tmp_path)
    for backend in ("fake", "omnilingual"):
        settings = _settings(
            tmp_path, stt=SttSelection(backend, tmp_path / "model", "en")
        )
        factory = ubuntu.UbuntuSessionFactory(
            stt_openers={backend: lambda selection: FakeEngine()},
            on_event=lambda event: None,
            microphones=FakeMicrophones(),
            source_factory=lambda config: object(),
            catalog=catalog,
            detector_factory=lambda: object(),
        )
        with factory(settings) as runtime:
            runtime.run()

    assert pauses == [384, 800]


def test_ubuntu_session_registers_persian_browser_name_only_when_allowed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class PersianSpeechController(FakeSpeechController):
        def events(self):  # type: ignore[no-untyped-def]
            yield TranscriptUpdate(0, "مرورگر رو باز کن", TranscriptStatus.FINAL, "fa")

    monkeypatch.setattr(ubuntu, "SpeechSessionController", PersianSpeechController)
    events: list[ubuntu.ApplicationEvent] = []
    factory = ubuntu.UbuntuSessionFactory(
        stt_openers={"fake": lambda selection: FakeEngine()},
        on_event=events.append,
        microphones=FakeMicrophones(),
        catalog=_catalog(tmp_path),
        detector_factory=lambda: object(),
        executor_factory=lambda paths: RecordingExecutor(),
    )
    allowed = _settings(
        tmp_path,
        allowed_apps=(AllowedApp("browser", "browser.desktop"),),
    )
    with factory(allowed) as runtime:
        runtime.run()
    assert [
        event.intent.target for event in events if isinstance(event, ActionRequest)
    ] == ["browser"]

    events.clear()
    with factory(_settings(tmp_path)) as runtime:
        runtime.run()
    assert not any(isinstance(event, ActionRequest) for event in events)


def test_session_uses_saved_aliases_and_unbound_name_collision_abstains(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class AliasSpeechController(FakeSpeechController):
        phrase = "Open my messenger"

        def events(self):  # type: ignore[no-untyped-def]
            yield TranscriptUpdate(0, self.phrase, TranscriptStatus.FINAL, "en")

    monkeypatch.setattr(ubuntu, "SpeechSessionController", AliasSpeechController)
    events: list[ubuntu.ApplicationEvent] = []
    factory = ubuntu.UbuntuSessionFactory(
        stt_openers={"fake": lambda selection: FakeEngine()},
        on_event=events.append,
        microphones=FakeMicrophones(),
        catalog=_catalog(tmp_path),
        detector_factory=lambda: object(),
        executor_factory=lambda paths: RecordingExecutor(),
    )
    allowed = _settings(
        tmp_path,
        app_spoken_aliases=(AppSpokenAliases("telegram.desktop", ("my messenger",)),),
    )
    with factory(allowed) as runtime:
        runtime.run()
    assert [
        event.intent.target for event in events if isinstance(event, ActionRequest)
    ] == ["telegram"]

    events.clear()
    AliasSpeechController.phrase = "Open Browser"
    collision = replace(
        allowed,
        app_spoken_aliases=(AppSpokenAliases("telegram.desktop", ("Browser",)),),
    )
    with factory(collision) as runtime:
        runtime.run()
    assert not any(isinstance(event, ActionRequest) for event in events)


def test_ubuntu_session_asks_which_permitted_browser_before_opening(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class BrowserSpeechController(FakeSpeechController):
        def events(self):  # type: ignore[no-untyped-def]
            yield TranscriptUpdate(0, "Open browser", TranscriptStatus.FINAL, "en")
            yield TranscriptUpdate(1, "Firefox", TranscriptStatus.FINAL, "en")

    directory = tmp_path / "data/applications"
    directory.mkdir(parents=True)
    for desktop_id, name in (
        ("chrome.desktop", "Google Chrome"),
        ("firefox.desktop", "Firefox"),
        ("private.desktop", "Private Browser"),
    ):
        (directory / desktop_id).write_text(
            "[Desktop Entry]\nType=Application\n"
            f"Name={name}\nExec=true\nCategories=Network;WebBrowser;\n",
            encoding="utf-8",
        )
    monkeypatch.setattr(ubuntu, "SpeechSessionController", BrowserSpeechController)
    events: list[ubuntu.ApplicationEvent] = []
    factory = ubuntu.UbuntuSessionFactory(
        stt_openers={"fake": lambda selection: FakeEngine()},
        on_event=events.append,
        microphones=FakeMicrophones(),
        catalog=XdgDesktopAppCatalog((tmp_path / "data",)),
        detector_factory=lambda: object(),
        executor_factory=lambda paths: RecordingExecutor(),
    )
    settings = _settings(
        tmp_path,
        allowed_apps=(
            AllowedApp("google-chrome", "chrome.desktop"),
            AllowedApp("firefox", "firefox.desktop"),
        ),
    )
    with factory(settings) as runtime:
        runtime.run()

    assert [
        event.intent.target for event in events if isinstance(event, ActionRequest)
    ] == ["firefox"]
    assert any(
        isinstance(event, ResponseRequest)
        and event.kind is ResponseKind.CHOOSE_APP
        and event.app_candidates == ("Firefox", "Google Chrome")
        for event in events
    )


def test_ubuntu_terminal_menu_reaches_authorized_dry_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class TerminalSpeechController(FakeSpeechController):
        def events(self):  # type: ignore[no-untyped-def]
            yield TranscriptUpdate(0, "Open Terminal", TranscriptStatus.FINAL, "en")
            yield TranscriptUpdate(1, "number two", TranscriptStatus.FINAL, "en")

    class Presence:
        def observe(self, app_id: str) -> WindowPresence:
            assert app_id == "terminal"
            return WindowPresence.OPEN

        def count(self, app_id: str) -> int:
            assert app_id == "terminal"
            return 1

    applications = tmp_path / "data/applications"
    applications.mkdir(parents=True)
    (applications / "org.gnome.Ptyxis.desktop").write_text(
        "[Desktop Entry]\nType=Application\nName=Terminal\nExec=ptyxis\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(ubuntu, "SpeechSessionController", TerminalSpeechController)
    events: list[ubuntu.ApplicationEvent] = []
    factory = ubuntu.UbuntuSessionFactory(
        stt_openers={"fake": lambda selection: FakeEngine()},
        on_event=events.append,
        microphones=FakeMicrophones(),
        catalog=XdgDesktopAppCatalog((tmp_path / "data",)),
        detector_factory=lambda: object(),
        window_presence_factory=lambda mapping: Presence(),
    )
    settings = _settings(
        tmp_path,
        allowed_apps=(AllowedApp("terminal", "org.gnome.Ptyxis.desktop"),),
    )
    with factory(settings) as runtime:
        runtime.run()
    assert any(
        isinstance(event, ResponseRequest)
        and event.kind is ResponseKind.CHOOSE_OPERATION
        for event in events
    )
    assert [
        event.intent.kind for event in events if isinstance(event, ActionRequest)
    ] == [CommandKind.NEW_APP_WINDOW]


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


def test_optional_foreground_observer_and_mascot_report_confirmed_action(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    action_completed = Event()

    class WaitingSpeechController(FakeSpeechController):
        def events(self):  # type: ignore[no-untyped-def]
            yield TranscriptUpdate(0, "Open Telegram", TranscriptStatus.FINAL, "en")
            assert action_completed.wait(1)

    monkeypatch.setattr(ubuntu, "SpeechSessionController", WaitingSpeechController)
    visuals: list[VisualPresentation] = []
    events: list[ubuntu.ApplicationEvent] = []

    def on_event(event: ubuntu.ApplicationEvent) -> None:
        events.append(event)
        if isinstance(event, ActionFeedback):
            action_completed.set()

    class TelegramObserver:
        def observe_active_app(self) -> str:
            return "telegram"

    factory = ubuntu.UbuntuSessionFactory(
        stt_openers={"fake": lambda selection: FakeEngine()},
        on_event=on_event,
        microphones=FakeMicrophones(),
        catalog=_catalog(tmp_path),
        detector_factory=lambda: object(),
        executor_factory=lambda paths: RecordingExecutor(),
        observer_factory=lambda app_ids, catalog: TelegramObserver(),
        visual_publish=visuals.append,
    )
    with factory(_settings(tmp_path, action_execution_enabled=True)) as runtime:
        runtime.run()

    assert any(
        isinstance(event, ActionFeedback) and event.outcome is ActionOutcome.CONFIRMED
        for event in events
    )
    assert VisualStatus.EXECUTING in {item.status for item in visuals}
    assert VisualStatus.CONFIRMED in {item.status for item in visuals}


def test_registered_existing_window_is_activated_without_relaunch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    action_completed = Event()

    class WaitingSpeechController(FakeSpeechController):
        def events(self):  # type: ignore[no-untyped-def]
            yield TranscriptUpdate(0, "Open Telegram", TranscriptStatus.FINAL, "en")
            assert action_completed.wait(1)

    class TelegramObserver:
        def observe_active_app(self) -> str:
            return "telegram"

    class TelegramActivator:
        def activate_existing_app(self, app_id: str) -> ActivationAttempt:
            activated.append(app_id)
            return ActivationAttempt.REQUESTED

    monkeypatch.setattr(ubuntu, "SpeechSessionController", WaitingSpeechController)
    events: list[ubuntu.ApplicationEvent] = []
    activated: list[str] = []
    launcher = RecordingExecutor()

    def on_event(event: ubuntu.ApplicationEvent) -> None:
        events.append(event)
        if isinstance(event, ActionFeedback):
            action_completed.set()

    def activator_factory(ids: dict[str, str]) -> TelegramActivator:
        assert ids == {"telegram": "telegram.desktop"}
        return TelegramActivator()

    factory = ubuntu.UbuntuSessionFactory(
        stt_openers={"fake": lambda selection: FakeEngine()},
        on_event=on_event,
        microphones=FakeMicrophones(),
        catalog=_catalog(tmp_path),
        detector_factory=lambda: object(),
        executor_factory=lambda paths: launcher,
        observer_factory=lambda app_ids, catalog: TelegramObserver(),
        activator_factory=activator_factory,
    )
    with factory(_settings(tmp_path, action_execution_enabled=True)) as runtime:
        runtime.run()

    assert activated == ["telegram"]
    assert launcher.requests == []
    assert any(
        isinstance(event, ActionFeedback) and event.outcome is ActionOutcome.CONFIRMED
        for event in events
    )


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


def test_chat_capability_requires_saved_permission_and_verification_dependencies(
    tmp_path: Path,
) -> None:
    catalog = _catalog(tmp_path)

    class ChatVerifier:
        def ready(self) -> bool:
            return True

        def verify(self, app_id: str, pid: int) -> bool:
            return True

    class TelegramObserver:
        def observe_active_app(self) -> str:
            return "telegram"

    def factory(
        *, verifier: ubuntu.ChatVerifier | None, identity: bool
    ) -> ubuntu.UbuntuSessionFactory:
        return ubuntu.UbuntuSessionFactory(
            stt_openers={"fake": lambda selection: FakeEngine()},
            on_event=lambda event: None,
            microphones=FakeMicrophones(),
            catalog=catalog,
            detector_factory=lambda: object(),
            executor_factory=lambda paths: RecordingExecutor(),
            observer_factory=lambda app_ids, catalog: TelegramObserver(),
            chat_verifier=verifier,
            focused_window=(lambda: ("telegram.desktop", 12)) if identity else None,
        )

    settings = _settings(tmp_path, action_execution_enabled=True)
    with factory(verifier=ChatVerifier(), identity=True)(settings) as runtime:
        gate = cast(LiveCommandRuntime, runtime)._gate
        assert gate is not None
        assert CommandKind.OPEN_CHAT not in gate.policy.supported_kinds

    permitted = replace(settings, allowed_chat_apps=("telegram",))
    with factory(verifier=None, identity=True)(permitted) as runtime:
        gate = cast(LiveCommandRuntime, runtime)._gate
        assert gate is not None
        assert CommandKind.OPEN_CHAT not in gate.policy.supported_kinds
    with factory(verifier=ChatVerifier(), identity=False)(permitted) as runtime:
        gate = cast(LiveCommandRuntime, runtime)._gate
        assert gate is not None
        assert CommandKind.OPEN_CHAT not in gate.policy.supported_kinds
    with factory(verifier=ChatVerifier(), identity=True)(permitted) as runtime:
        gate = cast(LiveCommandRuntime, runtime)._gate
        assert gate is not None
        assert gate.policy.allowed_chat_apps == frozenset({"telegram"})
        assert CommandKind.OPEN_CHAT in gate.policy.supported_kinds
