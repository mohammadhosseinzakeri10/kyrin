"""Build one Ubuntu live session from explicit settings and replaceable adapters."""

from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from pathlib import Path

from kyrin.actions.activate_or_launch import ActivateOrLaunchExecutor
from kyrin.actions.executor import ActionExecutor
from kyrin.actions.gate import ActionGate, ActionPolicy
from kyrin.actions.models import (
    ActionDecision,
    ActionFeedback,
    ActionNotice,
    ActionRequest,
    ActionResult,
)
from kyrin.actions.observed_executor import ObservedAppExecutor
from kyrin.actions.platforms.linux import LinuxDesktopEntryExecutor
from kyrin.actions.platforms.telegram import (
    ChatVerifier,
    TelegramSavedMessagesExecutor,
    WindowIdentityReader,
)
from kyrin.actions.window_control import WindowControlExecutor
from kyrin.app.controller import RuntimeSession
from kyrin.app.events import ApplicationEvent, SttDeviceReady
from kyrin.app.settings import AppSettings, SttSelection
from kyrin.audio.activity.silero_vad import SileroVad
from kyrin.audio.activity.voice_activity_detector import VoiceActivityDetector
from kyrin.audio.audio_backlog import BacklogNotice
from kyrin.audio.audio_errors import AudioCaptureStopError
from kyrin.audio.audio_input import AudioInput
from kyrin.audio.live_speech_pipeline import LiveSpeechEvent, LiveSpeechPipeline
from kyrin.audio.microphone.devices import (
    MicrophoneConfiguration,
    MicrophoneResolver,
    PortAudioMicrophoneResolver,
)
from kyrin.audio.playback_guard import PlaybackGuardInput
from kyrin.commands.coordinator import CommandCoordinator
from kyrin.commands.demo_interpreter import DemoCommandInterpreter
from kyrin.commands.models import (
    CommandEvent,
    CommandKind,
    ResponseChannel,
    ResponseRequest,
)
from kyrin.desktop.active_app import ActiveAppObserver
from kyrin.desktop.app_activation import ExistingAppActivator
from kyrin.desktop.platforms.xdg import XdgDesktopAppCatalog
from kyrin.desktop.spoken_app_names import CatalogSpokenAppResolver
from kyrin.desktop.window_control import AppWindowController
from kyrin.responses.models import SystemNotice, SystemNoticeKind
from kyrin.responses.presenter import PresentedResponse, ResponsePresenter
from kyrin.responses.speech import (
    ResponseSpeaker,
    SpeechSynthesisError,
    SpeechSynthesizer,
)
from kyrin.responses.system_notices import notice_for_backlog, notice_for_error
from kyrin.responses.visual_status import VisualPresentation, VisualStatusController
from kyrin.runtime.command_runtime import LiveCommandRuntime
from kyrin.runtime.speech_sessions import SpeechSessionController, SpeechSessionEnded
from kyrin.stt.backends.vosk import VoskEngine
from kyrin.stt.backends.whisper import WhisperEngine
from kyrin.stt.contracts import SpeechToTextEngine
from kyrin.stt.device import ComputeDevice, DevicePreference, SpeechToTextOptions
from kyrin.stt.errors import DeviceUnavailableError, SpeechToTextError
from kyrin.system_power.flow import PowerBackend, PowerPrompt, SystemPowerFlow
from kyrin.system_power.gnome import GnomePowerBackend

EngineOpener = Callable[[SttSelection], SpeechToTextEngine]
SourceFactory = Callable[[MicrophoneConfiguration], AudioInput]
EventSink = Callable[[ApplicationEvent], None]
ObserverFactory = Callable[[Mapping[str, str], XdgDesktopAppCatalog], ActiveAppObserver]
ActivatorFactory = Callable[[Mapping[str, str]], ExistingAppActivator]
WindowControllerFactory = Callable[[Mapping[str, str]], AppWindowController]


def standard_stt_openers(
    *,
    whisper_server_path: Path | None = None,
    whisper_gpu_server_path: Path | None = None,
) -> dict[str, EngineOpener]:
    """Use the existing offline adapters; no model or server is downloaded."""

    def open_vosk(selection: SttSelection) -> SpeechToTextEngine:
        if selection.device is DevicePreference.GPU:
            raise DeviceUnavailableError("the installed Vosk adapter supports CPU only")
        if selection.language == "auto":
            raise ValueError("Vosk needs a selected language model")
        return VoskEngine(selection.model_path, language=selection.language)

    def open_whisper(selection: SttSelection) -> SpeechToTextEngine:
        def open_on(path: Path, device: ComputeDevice) -> WhisperEngine:
            return WhisperEngine(
                path,
                selection.model_path,
                language=selection.language,
                compute_device=device,
            )

        if selection.device is DevicePreference.GPU:
            if whisper_gpu_server_path is None:
                raise DeviceUnavailableError("Whisper GPU runtime is not installed")
            try:
                return open_on(whisper_gpu_server_path, ComputeDevice.GPU)
            except SpeechToTextError as exc:
                raise DeviceUnavailableError(
                    f"Whisper GPU runtime could not start: {exc}"
                ) from exc
        if selection.device is DevicePreference.CPU:
            if whisper_server_path is None:
                raise FileNotFoundError("Whisper CPU runtime is not installed")
            return open_on(whisper_server_path, ComputeDevice.CPU)
        if whisper_gpu_server_path is not None:
            try:
                return open_on(whisper_gpu_server_path, ComputeDevice.GPU)
            except SpeechToTextError:
                if whisper_server_path is None:
                    raise
        if whisper_server_path is None:
            raise FileNotFoundError("Whisper CPU or GPU runtime is not installed")
        return open_on(whisper_server_path, ComputeDevice.CPU)

    return {"vosk": open_vosk, "whisper": open_whisper}


def _microphone_source(configuration: MicrophoneConfiguration) -> AudioInput:
    from kyrin.audio.microphone.input import MicrophoneInput

    return MicrophoneInput(
        configuration.index,
        configuration.audio_format,
        configuration.frames_per_chunk,
    )


class _VisualActionExecutor:
    """Mark execution only when the ordered action worker starts the call."""

    def __init__(
        self, executor: ActionExecutor, visual: VisualStatusController
    ) -> None:
        self._executor = executor
        self._visual = visual

    def execute(self, request: ActionRequest) -> ActionResult:
        self._visual.on_action_start(request)
        try:
            return self._executor.execute(request)
        except Exception:
            self._visual.on_action_error()
            raise


class UbuntuSessionFactory:
    """Own session resources while reusing the existing live command runtime.

    The event sink may be called by both audio and action threads. A graphical
    caller must hand these structured events to its own UI event loop.
    """

    def __init__(
        self,
        *,
        stt_openers: Mapping[str, EngineOpener],
        on_event: EventSink,
        microphones: MicrophoneResolver | None = None,
        source_factory: SourceFactory = _microphone_source,
        detector_factory: Callable[[], VoiceActivityDetector] = SileroVad,
        catalog: XdgDesktopAppCatalog | None = None,
        executor_factory: Callable[[Mapping[str, Path]], ActionExecutor] = (
            LinuxDesktopEntryExecutor
        ),
        observer_factory: ObserverFactory | None = None,
        activator_factory: ActivatorFactory | None = None,
        window_controller_factory: WindowControllerFactory | None = None,
        chat_verifier: ChatVerifier | None = None,
        focused_window: WindowIdentityReader | None = None,
        visual_publish: Callable[[VisualPresentation], None] | None = None,
        synthesizer: SpeechSynthesizer | None = None,
        power_backend_factory: Callable[[], PowerBackend] = GnomePowerBackend,
        system_power: SystemPowerFlow | None = None,
    ) -> None:
        self._stt_openers = dict(stt_openers)
        self._on_event = on_event
        self._microphones = microphones or PortAudioMicrophoneResolver()
        self._source_factory = source_factory
        self._detector_factory = detector_factory
        self._catalog = catalog or XdgDesktopAppCatalog()
        self._executor_factory = executor_factory
        self._observer_factory = observer_factory
        self._activator_factory = activator_factory
        self._window_controller_factory = window_controller_factory
        self._chat_verifier = chat_verifier
        self._focused_window = focused_window
        self._visual_publish = visual_publish
        self._synthesizer = synthesizer
        self._power_backend_factory = power_backend_factory
        self._system_power = system_power

    @contextmanager
    def __call__(self, settings: AppSettings) -> Iterator[RuntimeSession]:
        selection = settings.stt
        if selection is None:
            raise ValueError("select an STT model before starting listening")
        opener = self._stt_openers.get(selection.backend)
        if opener is None:
            raise ValueError(f"STT backend is not installed: {selection.backend}")

        # Resolve exact registered IDs. Missing apps stay in the action policy
        # but cannot acquire a launch path or a spoken registered name.
        entry_paths = self._catalog.entry_paths()
        installed = {
            binding.app_id: entry_paths[binding.desktop_id]
            for binding in settings.allowed_apps
            if binding.desktop_id in entry_paths
        }
        platform_ids = {
            binding.desktop_id: binding.app_id
            for binding in settings.allowed_apps
            if binding.app_id in installed
        }
        spoken_names = (
            CatalogSpokenAppResolver(
                self._catalog,
                platform_ids,
                aliases={"telegram": ("تلگرام", "تلیگرام")}
                if "telegram" in platform_ids.values()
                else None,
            )
            if platform_ids
            else None
        )
        coordinator = CommandCoordinator(
            DemoCommandInterpreter(spoken_names, wake_aliases=settings.wake_aliases)
        )
        chat_enabled = (
            settings.action_execution_enabled
            and "telegram" in settings.allowed_chat_apps
            and "telegram" in installed
            and self._observer_factory is not None
            and self._chat_verifier is not None
            and self._focused_window is not None
        )
        window_controls_available = self._window_controller_factory is not None
        supported_kinds = {CommandKind.OPEN_APP}
        if chat_enabled:
            supported_kinds.add(CommandKind.OPEN_CHAT)
        if window_controls_available:
            supported_kinds.update(
                {
                    CommandKind.RESTORE_APP,
                    CommandKind.MINIMIZE_APP,
                    CommandKind.CLOSE_APP_WINDOW,
                    CommandKind.MAXIMIZE_APP,
                    CommandKind.UNMAXIMIZE_APP,
                    CommandKind.FULLSCREEN_APP,
                    CommandKind.UNFULLSCREEN_APP,
                }
            )
        gate = ActionGate(
            ActionPolicy(
                allowed_apps=frozenset(
                    binding.app_id for binding in settings.allowed_apps
                ),
                allowed_chat_apps=frozenset({"telegram"})
                if chat_enabled
                else frozenset(),
                allowed_window_apps=frozenset(settings.allowed_window_apps),
                allowed_close_apps=frozenset(settings.allowed_close_apps),
                supported_kinds=frozenset(supported_kinds),
            )
        )
        observer = (
            self._observer_factory(platform_ids, self._catalog)
            if self._observer_factory is not None and platform_ids
            else None
        )

        # A missing microphone or unsupported explicit device fails before
        # capture. No alternative model or compute device is chosen silently.
        self._microphones.resolve(settings.microphone_device_key)
        engine = opener(selection)
        safe_to_close_engine = True
        speaker: ResponseSpeaker | None = None
        power_flow: SystemPowerFlow | None = None
        try:
            if (
                selection.device is DevicePreference.GPU
                and ComputeDevice.GPU not in engine.capabilities.supported_devices
            ):
                raise DeviceUnavailableError(
                    "the selected STT model and backend cannot run on GPU"
                )
            detector = self._detector_factory()
            presenter = ResponsePresenter(selection.language)
            visual = (
                VisualStatusController(
                    self._visual_publish, language=selection.language
                )
                if self._visual_publish is not None
                else None
            )
            if self._synthesizer is not None:
                speaker = ResponseSpeaker(self._synthesizer, on_error=self._on_event)

            def show_response(response: PresentedResponse) -> None:
                self._on_event(response)
                if (
                    speaker is not None
                    and response.channel is ResponseChannel.TEXT_AND_VOICE
                    and not speaker.submit(response)
                ):
                    self._on_event(SpeechSynthesisError("voice response queue is full"))

            def create_pipeline() -> LiveSpeechPipeline:
                configuration = self._microphones.resolve(
                    settings.microphone_device_key
                )
                source = self._source_factory(configuration)
                guarded = PlaybackGuardInput(source, speaker) if speaker else source
                return LiveSpeechPipeline(
                    guarded,
                    configuration.audio_format,
                    detector,
                    engine,
                    options=SpeechToTextOptions(
                        device=selection.device, language_hint=selection.language
                    ),
                    on_compute_device=lambda device: self._on_event(
                        SttDeviceReady(device)
                    ),
                )

            def show_live(event: LiveSpeechEvent) -> None:
                if visual is not None:
                    visual.on_live_event(event)
                self._on_event(event)
                if isinstance(event, BacklogNotice):
                    show_response(presenter.present(notice_for_backlog(event)))

            def show_command(event: CommandEvent) -> None:
                if visual is not None:
                    visual.on_command_event(event)
                self._on_event(event)
                if isinstance(event, ResponseRequest):
                    show_response(presenter.present(event))

            def show_action(output: ActionDecision | ActionFeedback) -> None:
                if visual is not None:
                    visual.on_action_output(output)
                self._on_event(output)
                if isinstance(output, (ActionNotice, ActionFeedback)):
                    show_response(presenter.present(output))

            def show_session_end(event: SpeechSessionEnded) -> None:
                self._on_event(event)
                if event.error is not None:
                    show_response(presenter.present(notice_for_error(event.error)))
                    if event.retry_delay_s is not None:
                        show_response(
                            presenter.present(
                                SystemNotice(
                                    SystemNoticeKind.LISTENING_RETRY,
                                    ResponseChannel.TEXT_ONLY,
                                )
                            )
                        )

            def show_power(prompt: PowerPrompt) -> None:
                self._on_event(prompt)
                show_response(
                    PresentedResponse(
                        None,
                        None,
                        prompt.text,
                        ResponseChannel.TEXT_AND_VOICE
                        if prompt.spoken
                        else ResponseChannel.TEXT_ONLY,
                        "en",
                    )
                )

            power_flow = self._system_power or SystemPowerFlow(
                self._power_backend_factory(),
                show_power,
                enabled=settings.action_execution_enabled
                and settings.system_power_enabled,
            )
            power_flow.configure(
                enabled=settings.action_execution_enabled
                and settings.system_power_enabled
            )
            power_flow.set_voice_ready(lambda: speaker is None or not speaker.is_active)
            if self._system_power is not None:
                power_flow.set_announcement(
                    lambda prompt: show_response(
                        PresentedResponse(
                            None,
                            None,
                            prompt.text,
                            ResponseChannel.TEXT_AND_VOICE,
                            "en",
                        )
                    )
                )

            executor: ActionExecutor | None = None
            if settings.action_execution_enabled:
                executor = self._executor_factory(installed)
                if observer is not None:
                    executor = ObservedAppExecutor(executor, observer)
                    if self._activator_factory is not None:
                        activator = self._activator_factory(
                            {
                                app_id: desktop_id
                                for desktop_id, app_id in platform_ids.items()
                            }
                        )
                        executor = ActivateOrLaunchExecutor(
                            executor, activator, observer
                        )
                if chat_enabled:
                    assert self._focused_window is not None
                    assert self._chat_verifier is not None
                    executor = TelegramSavedMessagesExecutor(
                        executor,
                        telegram_desktop_id=installed["telegram"].name,
                        identity_reader=self._focused_window,
                        verifier=self._chat_verifier,
                    )
                if self._window_controller_factory is not None:
                    controller = self._window_controller_factory(
                        {
                            app_id: desktop_id
                            for desktop_id, app_id in platform_ids.items()
                        }
                    )
                    executor = WindowControlExecutor(executor, controller)
                if visual is not None:
                    executor = _VisualActionExecutor(executor, visual)

            runtime = LiveCommandRuntime(
                SpeechSessionController(create_pipeline),
                coordinator=coordinator,
                gate=gate,
                observer=observer,
                executor=executor,
                on_live_event=show_live,
                on_command_event=show_command,
                on_action_output=show_action,
                on_session_end=show_session_end,
                system_power=power_flow,
            )
            yield runtime
        except AudioCaptureStopError:
            # The native STT worker may still own the model after a failed
            # capture stop. Match the terminal diagnostic's safety boundary.
            safe_to_close_engine = False
            raise
        finally:
            if self._system_power is not None and power_flow is not None:
                power_flow.cancel()
                power_flow.set_announcement(None)
            try:
                if speaker is not None:
                    speaker.close()
            finally:
                if safe_to_close_engine:
                    engine.close()
