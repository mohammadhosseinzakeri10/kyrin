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
from kyrin.app.platforms.ubuntu import UbuntuSessionFactory, standard_stt_openers
from kyrin.app.platforms.xdg_startup import (
    DESKTOP_FILE_ID,
    DesktopRegistrationError,
    XdgDesktopRegistration,
    user_desktop_paths,
)
from kyrin.app.qt.branding import LOGO_PATH
from kyrin.app.qt.single_instance import SingleInstanceError, SingleInstanceGuard
from kyrin.app.qt.translations import UiTranslations
from kyrin.app.qt.window import ControlWindow, EventBridge
from kyrin.app.settings_store import (
    JsonSettingsStore,
    SettingsError,
    linux_settings_path,
)
from kyrin.audio.microphone.devices import PortAudioMicrophoneResolver
from kyrin.desktop.active_app import ActiveAppObserver
from kyrin.desktop.platforms.gnome import GnomeShellActiveAppObserver
from kyrin.desktop.platforms.xdg import XdgDesktopAppCatalog
from kyrin.responses.gnome_status import GnomeVisualStatusSink


def _whisper_server_path() -> Path | None:
    """Use an explicit local binary or one installed on PATH; never download it."""
    configured = os.environ.get("KYRIN_WHISPER_SERVER")
    if configured:
        candidate = Path(configured)
        if (
            candidate.is_absolute()
            and candidate.is_file()
            and os.access(candidate, os.X_OK)
        ):
            return candidate
        return None
    found = shutil.which("whisper-server")
    return Path(found) if found else None


def _activate_window(window: ControlWindow) -> None:
    window.showNormal()
    window.raise_()
    window.activateWindow()


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
    server = _whisper_server_path()
    microphones = PortAudioMicrophoneResolver()
    events = EventBridge()
    catalog = XdgDesktopAppCatalog()
    visual_sink = GnomeVisualStatusSink() if GnomeVisualStatusSink.available() else None
    observer_factory = (
        _gnome_observer if GnomeShellActiveAppObserver.available() else None
    )
    factory = UbuntuSessionFactory(
        stt_openers=standard_stt_openers(whisper_server_path=server),
        on_event=events.publish,
        microphones=microphones,
        catalog=catalog,
        observer_factory=observer_factory,
        visual_publish=visual_sink.publish if visual_sink is not None else None,
    )
    controller = ApplicationController(factory)
    window = ControlWindow(
        settings,
        store,
        controller,
        microphones,
        events,
        whisper_server_available=server is not None,
        load_error=load_error,
        ui_translations=UiTranslations(linux_settings_path().parent),
        app_catalog=catalog,
        startup_registration=registration,
        startup_error=startup_error,
    )
    window.show()
    guard.activation_requested.connect(lambda: _activate_window(window))
    QTimer.singleShot(0, window.start_initial_session)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
