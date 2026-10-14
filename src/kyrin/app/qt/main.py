"""Optional Qt entry point; importing the core never requires Qt."""

import os
import shutil
import sys
import sysconfig
from collections.abc import Mapping
from pathlib import Path

from PySide6.QtCore import QStandardPaths, QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from kyrin.app.controller import ApplicationController
from kyrin.app.model_library import (
    ModelLibrary,
    ModelLibraryError,
    linux_model_library_path,
)
from kyrin.app.platforms.ubuntu import UbuntuSessionFactory, standard_stt_openers
from kyrin.app.platforms.xdg_startup import (
    DESKTOP_FILE_ID,
    DesktopRegistrationError,
    XdgDesktopRegistration,
    user_desktop_paths,
)
from kyrin.app.qt.branding import LOGO_PATH
from kyrin.app.qt.chat_verifier import QtChatVerifier
from kyrin.app.qt.ocr_setup import selected_ocr_engine
from kyrin.app.qt.screen_access import ScreenAccess
from kyrin.app.qt.screen_text_reader import ScreenTextReader
from kyrin.app.qt.single_instance import SingleInstanceError, SingleInstanceGuard
from kyrin.app.qt.translations import UiTranslations
from kyrin.app.qt.window import ControlWindow, EventBridge
from kyrin.app.settings import TtsSelection
from kyrin.app.settings_store import (
    JsonSettingsStore,
    SettingsError,
    linux_settings_path,
)
from kyrin.audio.microphone.devices import PortAudioMicrophoneResolver
from kyrin.commands.models import ResponseChannel
from kyrin.desktop.active_app import ActiveAppObserver
from kyrin.desktop.platforms.gnome import GnomeShellActiveAppObserver
from kyrin.desktop.platforms.gnome_activation import GnomeExistingAppActivator
from kyrin.desktop.platforms.gnome_window_control import GnomeAppWindowController
from kyrin.desktop.platforms.gnome_window_presence import GnomeAppWindowPresence
from kyrin.desktop.platforms.xdg import XdgDesktopAppCatalog
from kyrin.responses.gnome_status import GnomeVisualStatusSink
from kyrin.responses.presenter import PresentedResponse
from kyrin.responses.speech import (
    ResponseSpeaker,
    SpeechSynthesisError,
)
from kyrin.system_power.flow import InertPowerBackend, PowerPrompt, SystemPowerFlow
from kyrin.system_power.gnome import GnomePowerBackend
from kyrin.tts.runtime import ConfiguredSpeechSynthesizer
from kyrin.vision.ocr.contracts import OcrOptions


def _whisper_server_path(
    variable: str, command: str, *, scripts_directory: Path | None = None
) -> Path | None:
    """Find a configured or installed runtime without downloading it."""
    configured = os.environ.get(variable)
    if configured:
        candidate = Path(configured)
        if (
            candidate.is_absolute()
            and candidate.is_file()
            and os.access(candidate, os.X_OK)
        ):
            return candidate
        return None
    installed = (scripts_directory or Path(sysconfig.get_path("scripts"))) / command
    if installed.is_file() and os.access(installed, os.X_OK):
        return installed
    found = shutil.which(command)
    return Path(found) if found else None


def _activate_window(window: ControlWindow) -> None:
    window.showNormal()
    window.raise_()
    window.activateWindow()


def _tts_model_root(development_root: Path, installed_root: Path) -> Path:
    """Use the organized source-checkout catalog, retaining packaged fallback."""
    return development_root if development_root.is_dir() else installed_root


def _gnome_observer(
    app_ids: Mapping[str, str], catalog: XdgDesktopAppCatalog
) -> ActiveAppObserver:
    return GnomeShellActiveAppObserver(app_ids, catalog=catalog)


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("KYRIN")
    app.setApplicationDisplayName("KYRIN")
    app.setDesktopFileName(DESKTOP_FILE_ID)
    app.setWindowIcon(QIcon(str(LOGO_PATH)))
    app.setQuitOnLastWindowClosed(False)
    runtime_directory = QStandardPaths.writableLocation(
        QStandardPaths.StandardLocation.RuntimeLocation
    )
    if not runtime_directory:
        print("KYRIN needs a user-session runtime directory.", file=sys.stderr)
        return 1
    guard = SingleInstanceGuard(Path(runtime_directory) / "kyrin-control.sock")
    try:
        if not guard.start():
            return 0
    except SingleInstanceError as error:
        print(f"KYRIN could not start: {error}", file=sys.stderr)
        return 1
    app.aboutToQuit.connect(guard.close)
    screen_access = ScreenAccess(app)
    app.aboutToQuit.connect(screen_access.close)
    store = JsonSettingsStore(linux_settings_path())
    load_error: SettingsError | None = None
    try:
        settings = store.load()
    except SettingsError as error:
        settings = None
        load_error = error
    startup_error: DesktopRegistrationError | None = None
    registration: XdgDesktopRegistration | None = None
    try:
        menu_path, autostart_path = user_desktop_paths()
        executable = Path(sysconfig.get_path("scripts")) / "kyrin-desktop"
        registration = XdgDesktopRegistration(
            executable, menu_path, autostart_path, icon_path=LOGO_PATH
        )
    except DesktopRegistrationError as error:
        startup_error = error
    server = _whisper_server_path("KYRIN_WHISPER_SERVER", "whisper-server")
    gpu_server = _whisper_server_path("KYRIN_WHISPER_GPU_SERVER", "whisper-server-gpu")
    model_library = ModelLibrary(linux_model_library_path())
    development_command_store = (
        Path(__file__).resolve().parents[4]
        / "models/local/by-model/command-understanding/ollama"
    )
    development_tts_root = (
        Path(__file__).resolve().parents[4] / "models/local/by-model/tts"
    )
    try:
        model_library.cleanup_incomplete_imports()
    except ModelLibraryError as error:
        print(f"KYRIN model library: {error}", file=sys.stderr)
    microphones = PortAudioMicrophoneResolver()
    events = EventBridge()
    synthesizer = ConfiguredSpeechSynthesizer(
        settings.tts if settings is not None else TtsSelection(),
        settings.tts_languages if settings is not None else (),
    )
    speaker = ResponseSpeaker(synthesizer, on_error=events.publish)
    app.aboutToQuit.connect(speaker.close)
    power_flow = SystemPowerFlow(
        GnomePowerBackend(),
        events.publish,
        enabled=bool(
            settings
            and settings.action_execution_enabled
            and settings.system_power_enabled
        ),
        preview_backend=InertPowerBackend(),
    )
    power_flow.set_voice_ready(lambda: not speaker.is_active)

    def announce_power(prompt: PowerPrompt) -> None:
        response = PresentedResponse(
            None,
            None,
            prompt.speech_text or prompt.text,
            ResponseChannel.TEXT_AND_VOICE,
            "en",
        )
        if not speaker.submit(response):
            events.publish(SpeechSynthesisError("Voice output is busy"))

    power_flow.set_announcement(announce_power)

    def preview_tts(text: str, language: str, selection: TtsSelection) -> bool:
        return speaker.submit(
            PresentedResponse(
                None,
                None,
                text,
                ResponseChannel.TEXT_AND_VOICE,
                language,
            ),
            speak=lambda spoken, spoken_language: synthesizer.speak_preview(
                spoken, spoken_language, selection
            ),
        )

    catalog = XdgDesktopAppCatalog()
    active_identity = GnomeShellActiveAppObserver({})

    def focused_window() -> tuple[str, int] | None:
        observed = active_identity.read_active_window_identity()
        if observed is None:
            return None
        return observed.platform_app_id, observed.process_id

    ocr_root = linux_model_library_path().parent / "ocr" / "tesseract"
    screen_reader = ScreenTextReader(
        screen_access,
        selected_ocr_engine(settings.ocr if settings is not None else None, ocr_root),
        focused_window,
        OcrOptions("eng"),
        app,
    )
    app.aboutToQuit.connect(screen_reader.close)
    chat_verifier = QtChatVerifier(screen_access, screen_reader, app)
    visual_sink = GnomeVisualStatusSink() if GnomeVisualStatusSink.available() else None
    observer_factory = (
        _gnome_observer if GnomeShellActiveAppObserver.available() else None
    )
    activator_factory = (
        GnomeExistingAppActivator
        if observer_factory is not None and GnomeExistingAppActivator.available()
        else None
    )
    window_controller_factory = (
        GnomeAppWindowController if GnomeAppWindowController.available() else None
    )
    # The Shell extension can load after KYRIN starts at login. A GNOME
    # session keeps the adapter and its read calls fail safely until ready.
    window_presence_factory = (
        GnomeAppWindowPresence
        if "GNOME" in os.environ.get("XDG_CURRENT_DESKTOP", "").upper().split(":")
        else None
    )
    factory = UbuntuSessionFactory(
        stt_openers=standard_stt_openers(
            whisper_server_path=server, whisper_gpu_server_path=gpu_server
        ),
        on_event=events.publish,
        microphones=microphones,
        catalog=catalog,
        window_controller_factory=window_controller_factory,
        window_presence_factory=window_presence_factory,
        observer_factory=observer_factory,
        activator_factory=activator_factory,
        chat_verifier=chat_verifier,
        focused_window=focused_window,
        system_power=power_flow,
        response_speaker=speaker,
        visual_publish=visual_sink.publish if visual_sink is not None else None,
    )
    controller = ApplicationController(factory, power_flow)
    window = ControlWindow(
        settings,
        store,
        controller,
        microphones,
        events,
        whisper_server_available=server is not None,
        whisper_gpu_server_available=gpu_server is not None,
        model_library=model_library,
        suggested_command_store=(
            development_command_store if development_command_store.is_dir() else None
        ),
        tts_model_root=_tts_model_root(
            development_tts_root, linux_model_library_path().parent / "tts"
        ),
        configure_tts=synthesizer.configure,
        preview_tts=preview_tts,
        load_error=load_error,
        ui_translations=UiTranslations(linux_settings_path().parent),
        app_catalog=catalog,
        screen_access=screen_access,
        screen_reader=screen_reader,
        ocr_default_root=ocr_root,
        startup_registration=registration,
        startup_error=startup_error,
    )
    window.show()
    guard.activation_requested.connect(lambda: _activate_window(window))
    QTimer.singleShot(0, window.start_initial_session)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
