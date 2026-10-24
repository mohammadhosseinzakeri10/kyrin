"""The control-center permission is session-only and rejects malformed images."""

import json
from collections.abc import Callable
from pathlib import Path
from struct import pack

import pytest

PySide6 = pytest.importorskip("PySide6")
from PySide6.QtDBus import QDBusMessage  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from kyrin.app.permission_token import permission_token_path  # noqa: E402
from kyrin.app.qt.screen_access import SERVICE_NAME, ScreenAccess  # noqa: E402
from kyrin.app.qt.screen_access_page import ScreenAccessPage  # noqa: E402
from kyrin.app.qt.translations import UiTranslations  # noqa: E402
from kyrin.app.settings import OcrSelection  # noqa: E402
from kyrin.vision.screen_capture import IdentifiedWindowImage  # noqa: E402
from tests.desktop.test_backend_protocol import manifest  # noqa: E402

_PNG = b"\x89PNG\r\n\x1a\n" + b"pixels"


class FakeBus:
    def __init__(self, allow_name: bool = True) -> None:
        self.allow_name = allow_name
        self.registered: list[str] = []
        self.unregistered: list[str] = []

    def isConnected(self) -> bool:
        return True

    def registerService(self, name: str) -> bool:
        self.registered.append(name)
        return self.allow_name

    def unregisterService(self, name: str) -> bool:
        self.unregistered.append(name)
        return True


def _reply(*arguments: object) -> QDBusMessage:
    request = QDBusMessage.createMethodCall("org.gnome.Shell", "/x", "x.y", "test")
    response = request.createReply()
    response.setArguments(list(arguments))
    return response


class StubAccess(ScreenAccess):
    def __init__(
        self, replies: dict[str, QDBusMessage], *, allow_legacy_capture: bool = False
    ) -> None:
        self.replies = {
            "GetCapabilities": _reply(
                manifest(
                    "RequestPersistentSession",
                    "RevokeSession",
                    "CaptureActiveWindow",
                    "capture-geometry-v1",
                )
            ),
            **replies,
        }
        self.calls: list[str] = []
        super().__init__(allow_legacy_capture=allow_legacy_capture)

    def _call(
        self,
        member: str,
        timeout_ms: int,
        done: Callable[[QDBusMessage], None],
        token: str | None = None,
    ) -> None:
        self.calls.append(member)
        done(self.replies[member])


def test_session_permission_and_capture_use_the_owned_connection(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    app = QApplication.instance() or QApplication([])
    assert app is not None
    bus = FakeBus()
    monkeypatch.setattr(
        "kyrin.app.qt.screen_access.QDBusConnection.sessionBus", lambda: bus
    )
    access = StubAccess(
        {
            "RequestPersistentSession": _reply(True),
            "RevokeSession": _reply(True),
            "CaptureActiveWindow": _reply(
                "test.desktop",
                123,
                12,
                48,
                796,
                570,
                10,
                20,
                800,
                600,
                _PNG,
            ),
        },
        allow_legacy_capture=True,
    )
    assert bus.registered == [SERVICE_NAME]
    access.request_session()
    assert access.granted
    captured: list[IdentifiedWindowImage | None] = []
    access.capture(captured.append)
    assert captured[0] is not None
    assert captured[0].platform_app_id == "test.desktop"
    assert captured[0].capture_rect == (12, 48, 796, 570)
    assert captured[0].frame_rect == (10, 20, 800, 600)
    access.revoke()
    assert not access.granted
    access.capture(captured.append)
    assert captured[-1] is None
    assert access.calls == [
        "GetCapabilities",
        "RequestPersistentSession",
        "GetCapabilities",
        "CaptureActiveWindow",
        "RevokeSession",
    ]
    access.close()
    assert bus.unregistered == [SERVICE_NAME]


def test_unavailable_name_and_temporary_window_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    app = QApplication.instance() or QApplication([])
    assert app is not None
    bus = FakeBus(allow_name=False)
    monkeypatch.setattr(
        "kyrin.app.qt.screen_access.QDBusConnection.sessionBus", lambda: bus
    )
    denied = StubAccess({"RequestPersistentSession": _reply(True)})
    assert not denied.available
    denied.request_session()
    assert denied.calls == []
    denied.close()
    bus.allow_name = True
    access = StubAccess(
        {
            "RequestPersistentSession": _reply(True),
            "CaptureActiveWindow": _reply("window:8", 123, _PNG),
            "RevokeSession": _reply(True),
        }
    )
    access.request_session()
    captured: list[IdentifiedWindowImage | None] = []
    access.capture(captured.append)
    assert captured == [None]
    access.close()


@pytest.mark.parametrize(
    "unsupported", [None, "missing", "mapping", "desktop", "image"]
)
def test_capture_receives_only_supported_explicit_mapping(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    unsupported: str | None,
) -> None:
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    assert QApplication.instance() or QApplication([])
    monkeypatch.setattr(
        "kyrin.app.qt.screen_access.QDBusConnection.sessionBus", lambda: FakeBus()
    )
    png = b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\x0dIHDR" + pack(">II", 1000, 750)
    metadata_values = {
        "coordinate_space": "logical_desktop",
        "image_coordinate_space": "source_png_pixels",
        "mapping_source": "gnome-buffer-actor-v1",
        "monitor_id": 1,
        "scale_x": 1.25,
        "scale_y": 1.25,
        "padding": [0, 0, 0, 0],
        "window_token": "window-7",
        "capture_id": "capture-1",
        "captured_at": 100.0,
    }
    if unsupported == "missing":
        metadata_values.pop("mapping_source")
    elif unsupported == "mapping":
        metadata_values["mapping_source"] = "monitor-symmetric-guess"
    elif unsupported == "desktop":
        metadata_values["coordinate_space"] = "physical_desktop"
    elif unsupported == "image":
        metadata_values["image_coordinate_space"] = "ocr_pixels"
    metadata = json.dumps(metadata_values)
    access = StubAccess(
        {
            "RequestPersistentSession": _reply(True),
            "CaptureActiveWindow": _reply(
                "test.desktop",
                123,
                -1200,
                20,
                800,
                600,
                -1200,
                20,
                800,
                600,
                metadata,
                png,
            ),
        }
    )
    access.request_session()
    captured: list[IdentifiedWindowImage | None] = []
    access.capture(captured.append)
    if unsupported is not None:
        assert captured == [None]
        access.close()
        return
    assert captured[0] is not None
    assert captured[0].geometry is not None
    assert captured[0].geometry.monitor_id == 1
    assert captured[0].geometry.window_token == "window-7"
    assert captured[0].geometry.logical_rect == (-1200, 20, 800, 600)
    access.close()


def test_late_capture_reply_is_discarded_after_revoke(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    app = QApplication.instance() or QApplication([])
    assert isinstance(app, QApplication)
    bus = FakeBus()
    monkeypatch.setattr(
        "kyrin.app.qt.screen_access.QDBusConnection.sessionBus", lambda: bus
    )

    class DelayedCaptureAccess(StubAccess):
        pending_capture: Callable[[QDBusMessage], None] | None = None

        def _call(
            self,
            member: str,
            timeout_ms: int,
            done: Callable[[QDBusMessage], None],
            token: str | None = None,
        ) -> None:
            if member == "CaptureActiveWindow":
                self.pending_capture = done
                return
            super()._call(member, timeout_ms, done, token)

    access = DelayedCaptureAccess(
        {"RequestPersistentSession": _reply(True), "RevokeSession": _reply(True)}
    )
    access.request_session()
    captured: list[IdentifiedWindowImage | None] = []
    access.capture(captured.append)
    access.revoke()
    assert access.pending_capture is not None
    access.pending_capture(_reply("test.desktop", 123, _PNG))
    assert captured == [None]
    access.close()


def test_screen_page_revokes_access_without_saving_settings(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    app = QApplication.instance() or QApplication([])
    assert isinstance(app, QApplication)
    bus = FakeBus()
    monkeypatch.setattr(
        "kyrin.app.qt.screen_access.QDBusConnection.sessionBus", lambda: bus
    )
    access = StubAccess(
        {"RequestPersistentSession": _reply(True), "RevokeSession": _reply(True)}
    )
    page = ScreenAccessPage(access, UiTranslations(tmp_path))
    try:
        page.enabled_checkbox.click()
        assert access.granted
        assert page.enabled_checkbox.isChecked()
        page.enabled_checkbox.click()
        assert not access.granted
        assert not page.enabled_checkbox.isChecked()
        assert not permission_token_path("screen").exists()
        assert not (tmp_path / "settings.json").exists()
    finally:
        access.close()


def test_screen_page_selects_local_ocr_package_without_installing_it(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    app = QApplication.instance() or QApplication([])
    assert isinstance(app, QApplication)
    default = tmp_path / "default"
    alternate = tmp_path / "alternate"
    page = ScreenAccessPage(None, UiTranslations(tmp_path), ocr_default_root=default)
    try:
        assert page.selection() is None
        page.ocr_path.setText(str(alternate))
        assert page.selection() == OcrSelection("tesseract", alternate)
        assert page.has_unsaved_changes(None)
        page.ocr_path.setText(str(default))
        assert not page.has_unsaved_changes(None)
        assert not alternate.exists()
    finally:
        page.deleteLater()
        page.deleteLater()
        app.processEvents()


def test_screen_page_offers_downloaded_tesseract_packs(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    app = QApplication.instance() or QApplication([])
    assert isinstance(app, QApplication)
    candidates = tmp_path / "candidates"
    for name in ("fast", "best"):
        folder = candidates / "tesseract" / name
        folder.mkdir(parents=True)
        for language in ("eng", "fas"):
            (folder / f"{language}.traineddata").write_bytes(b"model")
    page = ScreenAccessPage(
        None,
        UiTranslations(tmp_path),
        ocr_default_root=tmp_path / "installed",
        ocr_candidates_root=candidates,
    )
    try:
        assert page.ocr_backend.count() == 3
        page.ocr_backend.setCurrentIndex(2)
        assert page.selection() == OcrSelection(
            "tesseract", candidates / "tesseract" / "best"
        )
    finally:
        page.deleteLater()
        app.processEvents()


def test_remembered_screen_token_survives_app_close(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    app = QApplication.instance() or QApplication([])
    assert isinstance(app, QApplication)
    monkeypatch.setattr(
        "kyrin.app.qt.screen_access.QDBusConnection.sessionBus", lambda: FakeBus()
    )
    access = StubAccess({"RequestPersistentSession": _reply(True)})
    access.request_session()
    saved = permission_token_path("screen").read_text(encoding="ascii")
    access.close()
    assert permission_token_path("screen").read_text(encoding="ascii") == saved
    reopened = StubAccess(
        {"RequestPersistentSession": _reply(True), "RevokeSession": _reply(True)}
    )
    try:
        assert reopened.remembered
        reopened.request_session()
        assert permission_token_path("screen").read_text(encoding="ascii") == saved
        reopened.revoke()
        assert not permission_token_path("screen").exists()
    finally:
        reopened.close()


def test_legacy_capture_is_rejected_by_default(monkeypatch, tmp_path):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    assert QApplication.instance() or QApplication([])
    monkeypatch.setattr(
        "kyrin.app.qt.screen_access.QDBusConnection.sessionBus", lambda: FakeBus()
    )
    access = StubAccess(
        {
            "RequestPersistentSession": _reply(True),
            "CaptureActiveWindow": _reply("test.desktop", 123, _PNG),
        }
    )
    access.request_session()
    captured = []
    access.capture(captured.append)
    assert captured == [None]
    access.close()


def test_screen_late_backend_has_bounded_probe_and_recovers(monkeypatch, tmp_path):
    from PySide6.QtCore import QTimer

    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    assert QApplication.instance() or QApplication([])
    monkeypatch.setattr(
        "kyrin.app.qt.screen_access.QDBusConnection.sessionBus", lambda: FakeBus()
    )
    timers = []
    monkeypatch.setattr(
        QTimer, "singleShot", lambda delay, owner, callback: timers.append(callback)
    )
    request = QDBusMessage.createMethodCall("org.gnome.Shell", "/x", "x.y", "test")
    unavailable = request.createErrorReply(
        "org.freedesktop.DBus.Error.UnknownObject", "not loaded"
    )
    access = StubAccess(
        {
            "GetCapabilities": unavailable,
            "RequestPersistentSession": _reply(True),
        }
    )
    errors = []
    access.error.connect(errors.append)
    assert access.transport_available and not access.available
    access.request_session()
    for _ in range(2):
        timers.pop(0)()
    assert not timers
    assert access.calls == ["GetCapabilities"] * 3
    assert access.backend_status.reason == "service_unavailable"
    assert errors == ["Screen backend: service_unavailable"]
    assert not permission_token_path("screen").exists()
    access.replies["GetCapabilities"] = _reply(
        manifest(
            "RequestPersistentSession",
            "RevokeSession",
            "CaptureActiveWindow",
            "capture-geometry-v1",
        )
    )
    access.request_session()
    assert access.available and access.granted
    assert access.calls[-2:] == ["GetCapabilities", "RequestPersistentSession"]
    access.close()


@pytest.mark.parametrize(
    "version,caps,reason",
    [
        (0, ["RequestPersistentSession", "RevokeSession"], "protocol_mismatch"),
        (
            1,
            ["RequestPersistentSession", "CaptureActiveWindow", "capture-geometry-v1"],
            "missing_capabilities:RevokeSession",
        ),
    ],
)
def test_screen_incompatible_backend_never_requests_permission(
    monkeypatch,
    tmp_path,
    version,
    caps,
    reason,
):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    assert QApplication.instance() or QApplication([])
    monkeypatch.setattr(
        "kyrin.app.qt.screen_access.QDBusConnection.sessionBus", lambda: FakeBus()
    )
    access = StubAccess({"GetCapabilities": _reply(manifest(*caps, version=version))})
    access.request_session()
    assert not access.granted
    assert access.calls == ["GetCapabilities"]
    assert access.backend_status.reason == reason
    assert not permission_token_path("screen").exists()
    access.close()


def test_legacy_handshake_requires_explicit_compatibility(monkeypatch, tmp_path):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    assert QApplication.instance() or QApplication([])
    monkeypatch.setattr(
        "kyrin.app.qt.screen_access.QDBusConnection.sessionBus", lambda: FakeBus()
    )
    request = QDBusMessage.createMethodCall("org.gnome.Shell", "/x", "x.y", "test")
    replies = {
        "GetCapabilities": request.createErrorReply(
            "org.freedesktop.DBus.Error.UnknownMethod", "old loaded module"
        ),
        "RequestPersistentSession": _reply(True),
        "CaptureActiveWindow": _reply("test.desktop", 123, _PNG),
    }
    for allow_legacy in (False, True):
        access = StubAccess(replies, allow_legacy_capture=allow_legacy)
        access.request_session()
        assert access.granted is allow_legacy
        captured = []
        access.capture(captured.append)
        assert (captured[0] is not None) is allow_legacy
        access.close()


@pytest.mark.parametrize("stop", ["revoke", "close", "cancel"])
def test_late_probe_cannot_restart_permission_after_stop(monkeypatch, tmp_path, stop):
    from time import monotonic

    from PySide6.QtCore import QTimer

    from kyrin.operations import Operation, activate

    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    assert QApplication.instance() or QApplication([])
    monkeypatch.setattr(
        "kyrin.app.qt.screen_access.QDBusConnection.sessionBus", lambda: FakeBus()
    )
    timers = []
    monkeypatch.setattr(
        QTimer, "singleShot", lambda delay, owner, callback: timers.append(callback)
    )
    request = QDBusMessage.createMethodCall("org.gnome.Shell", "/x", "x.y", "test")
    access = StubAccess(
        {
            "GetCapabilities": request.createErrorReply(
                "org.freedesktop.DBus.Error.UnknownObject", "not loaded"
            ),
            "RevokeSession": _reply(True),
        }
    )
    operation = Operation(monotonic() + 10)
    with activate(operation):
        access.request_session()
    assert len(timers) == 1
    if stop == "cancel":
        operation.cancel()
    else:
        getattr(access, stop)()
    access.replies["GetCapabilities"] = _reply(
        manifest(
            "RequestPersistentSession",
            "RevokeSession",
            "CaptureActiveWindow",
            "capture-geometry-v1",
        )
    )
    timers.pop()()
    assert "RequestPersistentSession" not in access.calls
    assert not access.granted
    assert not permission_token_path("screen").exists()
    access.close()


def test_backend_loss_keeps_remembered_permission_and_allows_recovery(
    monkeypatch, tmp_path
):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    assert QApplication.instance() or QApplication([])
    monkeypatch.setattr(
        "kyrin.app.qt.screen_access.QDBusConnection.sessionBus", lambda: FakeBus()
    )
    access = StubAccess({"RequestPersistentSession": _reply(True)})
    access.request_session()
    token = permission_token_path("screen").read_bytes()
    compatible = access.replies["GetCapabilities"]
    access.replies["GetCapabilities"] = _reply(
        manifest("CaptureActiveWindow", version=0)
    )
    captured = []
    access.capture(captured.append)
    assert captured == [None]
    assert not access.granted
    assert access.remembered
    assert permission_token_path("screen").read_bytes() == token
    access.replies["GetCapabilities"] = compatible
    access.request_session()
    assert access.granted
    assert permission_token_path("screen").read_bytes() == token
    access.close()
