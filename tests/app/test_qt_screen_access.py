"""The control-center permission is session-only and rejects malformed images."""

from collections.abc import Callable
from pathlib import Path

import pytest

PySide6 = pytest.importorskip("PySide6")
from PySide6.QtDBus import QDBusMessage  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from kyrin.app.permission_token import permission_token_path  # noqa: E402
from kyrin.app.qt.screen_access import SERVICE_NAME, ScreenAccess  # noqa: E402
from kyrin.app.qt.screen_access_page import ScreenAccessPage  # noqa: E402
from kyrin.app.qt.translations import UiTranslations  # noqa: E402
from kyrin.vision.screen_capture import IdentifiedWindowImage  # noqa: E402

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
    def __init__(self, replies: dict[str, QDBusMessage]) -> None:
        self.replies = replies
        self.calls: list[str] = []
        super().__init__()

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
            "CaptureActiveWindow": _reply("test.desktop", 123, _PNG),
        }
    )
    assert bus.registered == [SERVICE_NAME]
    access.request_session()
    assert access.granted
    captured: list[IdentifiedWindowImage | None] = []
    access.capture(captured.append)
    assert captured[0] is not None
    assert captured[0].platform_app_id == "test.desktop"
    access.revoke()
    assert not access.granted
    access.capture(captured.append)
    assert captured[-1] is None
    assert access.calls == [
        "RequestPersistentSession",
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
