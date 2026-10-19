"""Build one Ubuntu live session from explicit settings and replaceable adapters."""

import logging
import sqlite3
from collections.abc import Callable, Iterator, Mapping
from contextlib import AbstractContextManager, ExitStack, contextmanager
from pathlib import Path

from kyrin.actions.activate_or_launch import ActivateOrLaunchExecutor
from kyrin.actions.executor import ActionExecutor
from kyrin.actions.gate import ActionGate, ActionPolicy
from kyrin.actions.models import (
    ActionDecision,
    ActionFeedback,
    ActionNotice,
    ActionOutcome,
    ActionRequest,
    ActionResult,
)
from kyrin.actions.observed_executor import ObservedAppExecutor
from kyrin.actions.platforms.desktop_scroll import DesktopScrollExecutor
from kyrin.actions.platforms.linux import LinuxDesktopEntryExecutor
from kyrin.actions.platforms.open_windows import OpenWindowPickerExecutor
from kyrin.actions.platforms.ptyxis import PtyxisActionExecutor
from kyrin.actions.platforms.telegram import (
    ChatVerifier,
    TelegramSavedMessagesExecutor,
    WindowIdentityReader,
)
from kyrin.actions.telegram_selection import TelegramChatSelection
from kyrin.actions.window_control import WindowControlExecutor
from kyrin.app.controller import RuntimeSession
from kyrin.app.events import ApplicationEvent, AudioCaptureReady, SttDeviceReady
from kyrin.app.platforms.pipewire_aec import PipeWireEchoCancellation
from kyrin.app.settings import AppSettings, CommandModelSelection, SttSelection
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
from kyrin.commands.interpreter import CommandInterpreter
from kyrin.commands.model_interpreter import ModelAssistedInterpreter
from kyrin.commands.models import (
    CommandEvent,
    CommandKind,
    ResponseChannel,
    ResponseRequest,
)
from kyrin.commands.ollama_engine import OllamaCommandEngine
from kyrin.commands.ollama_models import installed_ollama_models
from kyrin.commands.ollama_server import LocalOllamaServer
from kyrin.desktop.active_app import ActiveAppObserver
from kyrin.desktop.app_activation import ExistingAppActivator
from kyrin.desktop.platforms.xdg import XdgDesktopAppCatalog
from kyrin.desktop.spoken_app_names import CatalogSpokenAppResolver
from kyrin.desktop.window_control import AppWindowController
from kyrin.desktop.window_presence import AppWindowPresence
from kyrin.memory.history import SqliteConversationHistory, default_history_path
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
from kyrin.stt.contracts import CancellableSpeechToTextEngine, SpeechToTextEngine
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
WindowPresenceFactory = Callable[[Mapping[str, str]], AppWindowPresence]
CommandServerFactory = Callable[[CommandModelSelection], AbstractContextManager[str]]
_LOGGER = logging.getLogger(__name__)


def _command_server(selection: CommandModelSelection) -> AbstractContextManager[str]:
    return LocalOllamaServer(selection.store_path, selection.model)


def standard_stt_openers(
    *,
    whisper_server_path: Path | None = None,
    whisper_gpu_server_path: Path | None = None,
    omnilingual_python: Path | None = None,
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

    def open_omnilingual(selection: SttSelection) -> SpeechToTextEngine:
        from kyrin.stt.backends.omnilingual import OmnilingualEngine

        if omnilingual_python is None:
            raise FileNotFoundError("Omnilingual ASR runtime is not installed")
        return OmnilingualEngine(
            omnilingual_python,
            selection.model_path,
            language=selection.language,
            device=selection.device,
        )

    return {
        "vosk": open_vosk,
        "whisper": open_whisper,
        "omnilingual": open_omnilingual,
    }


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
        window_presence_factory: WindowPresenceFactory | None = None,
        chat_verifier: ChatVerifier | None = None,
        focused_window: WindowIdentityReader | None = None,
        visual_publish: Callable[[VisualPresentation], None] | None = None,
        synthesizer: SpeechSynthesizer | None = None,
        response_speaker: ResponseSpeaker | None = None,
        power_backend_factory: Callable[[], PowerBackend] = GnomePowerBackend,
        system_power: SystemPowerFlow | None = None,
        command_server_factory: CommandServerFactory = _command_server,
        echo_cancellation_factory: Callable[[], PipeWireEchoCancellation] | None = None,
        voice_standby: bool = False,
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
        self._window_presence_factory = window_presence_factory
        self._chat_verifier = chat_verifier
        self._focused_window = focused_window
        self._visual_publish = visual_publish
        self._synthesizer = synthesizer
        self._response_speaker = response_speaker
        self._power_backend_factory = power_backend_factory
        self._system_power = system_power
        self._command_server_factory = command_server_factory
        self._echo_cancellation_factory = echo_cancellation_factory
        self._voice_standby = voice_standby

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
                aliases={
                    app_id: names
                    for app_id, names in {
                        "telegram": (
                            "تلگرام",
                            "تلیگرام",
                            "تيليغرام",
                            "ٹیلیگرام",
                        ),
                        "browser": ("مرورگر",),
                    }.items()
                    if app_id in platform_ids.values()
                },
                registered_aliases={
                    item.platform_id: item.aliases
                    for item in settings.app_spoken_aliases
                },
            )
            if platform_ids
            else None
        )
        desktop_ids = {
            app_id: desktop_id for desktop_id, app_id in platform_ids.items()
        }
        window_presence = (
            self._window_presence_factory(desktop_ids)
            if self._window_presence_factory is not None
            else None
        )
        terminal_app_id = platform_ids.get("org.gnome.Ptyxis.desktop")
        rules = DemoCommandInterpreter(
            spoken_names,
            wake_aliases=settings.wake_aliases,
            browser_candidates=(
                spoken_names.browser_candidates() if spoken_names else ()
            ),
            allowed_window_apps=frozenset(settings.allowed_window_apps),
            scroll_any_focused_app=settings.allow_desktop_scroll,
            allowed_close_apps=frozenset(settings.allowed_close_apps),
            window_presence=window_presence,
            terminal_app_id=terminal_app_id,
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
        if terminal_app_id is not None:
            supported_kinds.update(
                {
                    CommandKind.NEW_APP_WINDOW,
                    CommandKind.NEW_APP_TAB,
                    CommandKind.APP_PREFERENCES,
                }
            )
            if window_presence is not None:
                supported_kinds.update(
                    {
                        CommandKind.SHOW_APP_WINDOWS,
                        CommandKind.SELECT_APP_WINDOW,
                        CommandKind.CLOSE_SHOWN_WINDOW,
                        CommandKind.HIDE_APP_WINDOWS,
                    }
                )
        if window_presence is not None and settings.allowed_window_apps:
            supported_kinds.update(
                {
                    CommandKind.SHOW_ALL_WINDOWS,
                    CommandKind.SELECT_APP_WINDOW,
                    CommandKind.CLOSE_SHOWN_WINDOW,
                    CommandKind.HIDE_APP_WINDOWS,
                    CommandKind.SELECT_OPEN_APP_WINDOW,
                }
            )
        if chat_enabled:
            supported_kinds.update({
                CommandKind.OPEN_CHAT,
                CommandKind.TELEGRAM_VIEW,
                CommandKind.TELEGRAM_SETTINGS,
                CommandKind.TELEGRAM_SEARCH_FOCUS,
                CommandKind.TELEGRAM_SEARCH,
            })
        if settings.allow_desktop_scroll and self._focused_window is not None:
            supported_kinds.update({CommandKind.SCROLL_UP, CommandKind.SCROLL_DOWN})
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
                allow_focused_scroll=(
                    settings.allow_desktop_scroll and self._focused_window is not None
                ),
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
        speaker: ResponseSpeaker | None = self._response_speaker
        echo_cancel: PipeWireEchoCancellation | None = None
        power_flow: SystemPowerFlow | None = None
        command_server: AbstractContextManager[str] | None = None
        history: SqliteConversationHistory | None = None
        try:
            if (
                selection.device is DevicePreference.GPU
                and ComputeDevice.GPU not in engine.capabilities.supported_devices
            ):
                raise DeviceUnavailableError(
                    "the selected STT model and backend cannot run on GPU"
                )
            interpreter: CommandInterpreter = rules
            command_selection = settings.command_model
            if command_selection is not None:
                if spoken_names is None:
                    raise ValueError(
                        "select an allowed installed app before using a command model"
                    )
                if command_selection.model not in installed_ollama_models(
                    command_selection.store_path
                ):
                    raise ValueError(
                        "selected command model is incomplete or unavailable"
                    )
                command_server = self._command_server_factory(command_selection)
                endpoint = command_server.__enter__()
                interpreter = ModelAssistedInterpreter(
                    rules,
                    OllamaCommandEngine(
                        endpoint, command_selection.model, command_selection.device
                    ),
                    spoken_names,
                    allowed_apps=frozenset(installed),
                    supported_chat_apps=frozenset({"telegram"})
                    if "telegram" in settings.allowed_chat_apps
                    else frozenset(),
                    action_review=rules.review_model_action,
                )
            try:
                history = SqliteConversationHistory(default_history_path())
            except (OSError, ValueError, sqlite3.Error) as exc:
                _LOGGER.warning("Conversation history is unavailable: %s", exc)
            recent_utterances: Callable[[], tuple[str, ...]] | None = None
            if history is not None:
                history_store = history

                def read_recent_utterances() -> tuple[str, ...]:
                    try:
                        return tuple(
                            turn.text[:240] for turn in history_store.recent(limit=6)
                        )
                    except (OSError, sqlite3.Error) as exc:
                        _LOGGER.warning("Conversation history is unavailable: %s", exc)
                        return ()

                recent_utterances = read_recent_utterances
            coordinator = CommandCoordinator(
                interpreter,
                recent_utterances=recent_utterances,
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
            if speaker is None and self._synthesizer is not None:
                speaker = ResponseSpeaker(self._synthesizer, on_error=self._on_event)
            if (
                speaker is not None
                and settings.microphone_device_key is None
                and self._echo_cancellation_factory is not None
            ):
                candidate = self._echo_cancellation_factory()
                if candidate.start():
                    echo_cancel = candidate
                else:
                    _LOGGER.warning(
                        "PipeWire echo cancellation unavailable; "
                        "playback guard remains active"
                    )

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
                echo_source = echo_cancel.input() if echo_cancel is not None else None
                source = (
                    echo_source
                    if echo_source is not None
                    else self._source_factory(configuration)
                )
                guarded = (
                    source
                    if echo_cancel is not None or speaker is None
                    else PlaybackGuardInput(source, speaker)
                )
                return LiveSpeechPipeline(
                    guarded,
                    echo_source.audio_format
                    if echo_source is not None
                    else configuration.audio_format,
                    detector,
                    engine,
                    options=SpeechToTextOptions(
                        device=selection.device,
                        language_hint=selection.language,
                        vocabulary_hints=(
                            spoken_names.vocabulary_hints()
                            if spoken_names is not None
                            and engine.capabilities.supports_vocabulary_hints
                            else ()
                        ),
                    ),
                    # Omnilingual infers complete utterances. A 640 ms pause
                    # inside a verified Persian sentence split it at the
                    # generic 384 ms boundary and corrupted the first word.
                    pause_confirm_ms=(
                        800 if selection.backend == "omnilingual" else 384
                    ),
                    on_compute_device=lambda device: self._on_event(
                        SttDeviceReady(device)
                    ),
                    on_audio_ready=lambda: self._on_event(AudioCaptureReady()),
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
                if (
                    isinstance(output, ActionFeedback)
                    and output.error_code == "chat_selection_pending"
                ):
                    return
                if visual is not None:
                    visual.on_action_output(output)
                self._on_event(output)
                if (
                    isinstance(output, ActionFeedback)
                    and output.intent.kind
                    in (CommandKind.SHOW_APP_WINDOWS, CommandKind.SHOW_ALL_WINDOWS)
                    and output.outcome is ActionOutcome.LAUNCH_ACCEPTED
                ):
                    return
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
            power_flow.set_voice_ready(
                lambda: (
                    echo_cancel is not None or speaker is None or not speaker.is_active
                )
            )
            if self._system_power is not None and self._response_speaker is None:
                power_flow.set_announcement(
                    lambda prompt: show_response(
                        PresentedResponse(
                            None,
                            None,
                            prompt.speech_text or prompt.text,
                            ResponseChannel.TEXT_AND_VOICE,
                            "en",
                        )
                    )
                )

            def show_chat_selection_prompt(event: ResponseRequest) -> None:
                if visual is not None:
                    visual.on_chat_selection_prompt(event)
                self._on_event(event)
                show_response(presenter.present(event))

            chat_selection = (
                TelegramChatSelection(show_chat_selection_prompt, show_action)
                if chat_enabled and settings.action_execution_enabled
                else None
            )
            executor: ActionExecutor | None = None
            if settings.action_execution_enabled:
                executor = self._executor_factory(installed)
                if terminal_app_id is not None:
                    executor = PtyxisActionExecutor(
                        executor,
                        terminal_app_id,
                        installed[terminal_app_id],
                        window_presence,
                    )
                if window_presence is not None and settings.allowed_window_apps:
                    executor = OpenWindowPickerExecutor(
                        executor,
                        {
                            app_id: desktop_ids[app_id]
                            for app_id in installed
                            if app_id in desktop_ids
                        },
                        {
                            app_id: desktop_ids[app_id]
                            for app_id in settings.allowed_close_apps
                            if app_id in desktop_ids
                            and app_id in settings.allowed_window_apps
                        },
                    )
                if observer is not None:
                    executor = ObservedAppExecutor(executor, observer)
                    if self._activator_factory is not None:
                        activator = self._activator_factory(desktop_ids)
                        executor = ActivateOrLaunchExecutor(
                            executor, activator, observer
                        )
                if chat_enabled:
                    assert self._focused_window is not None
                    assert self._chat_verifier is not None
                    telegram_executor = TelegramSavedMessagesExecutor(
                        executor,
                        telegram_desktop_id=installed["telegram"].name,
                        identity_reader=self._focused_window,
                        verifier=self._chat_verifier,
                        selection=chat_selection,
                        remember_pointer=settings.remember_telegram_pointer,
                    )
                    if chat_selection is not None:
                        chat_selection.set_completion(
                            telegram_executor.complete_selection
                        )
                        chat_selection.set_page_navigation(
                            telegram_executor.next_search_page
                        )
                    executor = telegram_executor
                if settings.allow_desktop_scroll and self._focused_window is not None:
                    executor = DesktopScrollExecutor(
                        executor,
                        desktop_ids={},
                        identity_reader=self._focused_window,
                        allow_any_focused_app=True,
                    )
                if self._window_controller_factory is not None:
                    controller = self._window_controller_factory(desktop_ids)
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
                scroll_focus_reader=(
                    self._focused_window if settings.allow_desktop_scroll else None
                ),
                system_power=power_flow,
                telegram_selection=chat_selection,
                history=history,
                voice_standby=self._voice_standby,
                on_voice_mode=self._on_event,
            )
            yield runtime
        except AudioCaptureStopError:
            # The native STT worker may still own the model after a failed
            # capture stop. Terminate an owned child process without closing
            # an engine whose session may still be active in another thread.
            safe_to_close_engine = False
            if isinstance(engine, CancellableSpeechToTextEngine):
                engine.cancel_pending_inference()
            raise
        finally:
            # ExitStack runs every callback even when an earlier close fails.
            # Register in reverse order so the STT engine remains last.
            with ExitStack() as cleanup:
                if safe_to_close_engine:
                    cleanup.callback(engine.close)
                if speaker is not None and speaker is not self._response_speaker:
                    cleanup.callback(speaker.close)
                if self._system_power is not None:
                    cleanup.callback(
                        self._system_power.set_voice_ready,
                        lambda: speaker is None or not speaker.is_active,
                    )
                if echo_cancel is not None:
                    cleanup.callback(echo_cancel.close)
                if self._system_power is not None and power_flow is not None:
                    if self._response_speaker is None:
                        cleanup.callback(power_flow.set_announcement, None)
                    cleanup.callback(power_flow.cancel)
                if command_server is not None:
                    cleanup.callback(command_server.__exit__, None, None, None)
                if history is not None:
                    cleanup.callback(history.close)
