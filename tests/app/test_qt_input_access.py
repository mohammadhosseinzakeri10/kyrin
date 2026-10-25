"""Settings jobs remain asynchronous and cannot publish readiness after cancel."""

from threading import Event, get_ident
from time import monotonic, sleep
from typing import Any, cast

import pytest

pytest.importorskip("PySide6")
from PySide6.QtCore import QObject, Slot  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from kyrin.actions.platforms.input_session import InputSessionService  # noqa: E402
from kyrin.app.qt.input_access import InputSetupJob  # noqa: E402


@pytest.mark.parametrize("cancel", [False, True])
def test_async_setup_result_and_cancellation(cancel: bool) -> None:
    app = QApplication.instance() or QApplication([])
    entered, release = Event(), Event()
    result: list[dict[str, Any]] = []
    gui_thread = get_ident()

    class Service:
        def prepare(self, capability: str) -> dict[str, Any]:
            assert capability == "desktop_scroll"
            assert get_ident() != gui_thread
            entered.set()
            assert release.wait(2)
            return {"state": "ready", "devices": 2}

        def disconnect(self) -> None:
            release.set()

    class Receiver(QObject):
        @Slot(object)
        def receive(self, value: dict[str, Any]) -> None:
            assert get_ident() == gui_thread
            result.append(value)

    receiver = Receiver()
    job = InputSetupJob(
        cast(InputSessionService, Service()), "desktop_scroll", receiver
    )
    job.finished.connect(receiver.receive)
    job.start()
    assert entered.wait(1)
    assert not result
    if cancel:
        job.kill()
    else:
        release.set()
    deadline = monotonic() + 2
    while not result and monotonic() < deadline:
        app.processEvents()
        sleep(0.005)
    assert result[0]["state"] == ("disconnected" if cancel else "ready")
    job._worker.join(1)
    assert not job._worker.is_alive()
    job.deleteLater()
    app.processEvents()
