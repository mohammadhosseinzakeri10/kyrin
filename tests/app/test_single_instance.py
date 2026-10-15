"""Local activation keeps a second control process from starting audio."""

# ruff: noqa: E402

import socket
from pathlib import Path
from uuid import uuid4

import pytest

pytest.importorskip("PySide6")
from PySide6.QtWidgets import QApplication

from kyrin.app.qt.single_instance import SingleInstanceGuard


@pytest.fixture
def application(monkeypatch: pytest.MonkeyPatch) -> QApplication:
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    existing = QApplication.instance()
    return existing if isinstance(existing, QApplication) else QApplication([])


@pytest.fixture(autouse=True)
def require_local_sockets(tmp_path: Path) -> None:
    """The Qt integration test needs Unix sockets, unavailable in some sandboxes."""
    with socket.socket(socket.AF_UNIX) as probe:
        try:
            probe.bind(str(tmp_path / "socket-probe"))
        except PermissionError:
            pytest.skip("Unix sockets are unavailable in this test environment")


def test_second_instance_activates_first(application: QApplication) -> None:
    address = Path("/tmp") / f"kyrin-test-{uuid4().hex[:12]}.sock"
    primary = SingleInstanceGuard(address)
    secondary = SingleInstanceGuard(address)
    activations: list[str] = []
    primary.activation_requested.connect(lambda: activations.append("show"))
    try:
        assert primary.start()
        assert not secondary.start()
        application.processEvents()
        assert activations == ["show"]
    finally:
        primary.close()
        secondary.close()
        address.unlink(missing_ok=True)


def test_abandoned_socket_is_recovered(application: QApplication) -> None:
    address = Path("/tmp") / f"kyrin-test-{uuid4().hex[:12]}.sock"
    address.touch()
    primary = SingleInstanceGuard(address)
    try:
        assert primary.start()
    finally:
        primary.close()
        address.unlink(missing_ok=True)
