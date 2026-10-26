"""The worker receives only the decision of its own current Qt dialog."""

from collections.abc import Callable
from dataclasses import replace
from threading import Thread
from time import monotonic, sleep

import pytest

pytest.importorskip("PySide6")
from PySide6.QtWidgets import QApplication, QDialog, QLabel, QPushButton  # noqa: E402

from kyrin.actions.control_policy import (  # noqa: E402
    ControlCapability,
    ControlConfirmation,
    ControlEvidence,
)
from kyrin.actions.models import ActionKey  # noqa: E402
from kyrin.app.qt.control_confirmation import QtControlConfirmation  # noqa: E402
from kyrin.desktop.window_observation import WindowObservation  # noqa: E402
from kyrin.operations import budget  # noqa: E402


def prompt() -> ControlConfirmation:
    now = monotonic()
    return ControlConfirmation(
        ActionKey(1, 1),
        ControlCapability.ACTIVATE,
        ControlEvidence("Mode <b>test</b>", "ocr", None, None, (10, 20)),
        WindowObservation("app.desktop", 42, "window-7", "initial", now, now + 10),
        None,
        "fa",
    )


def worker(app: QApplication, work: Callable[[], bool], ui: Callable[[], None]) -> bool:
    results: list[bool] = []
    thread = Thread(target=lambda: results.append(work()))
    thread.start()
    deadline = monotonic() + 2
    while thread.is_alive() and monotonic() < deadline:
        app.processEvents()
        ui()
        sleep(0.002)
    thread.join(0.1)
    assert not thread.is_alive()
    app.processEvents()
    return results[0]


@pytest.mark.parametrize("approve", [True, False])
@pytest.mark.parametrize("close", [False, True])
def test_real_dialog_requires_explicit_button_and_dismisses(
    approve: bool, close: bool
) -> None:
    app = QApplication.instance() or QApplication([])
    assert isinstance(app, QApplication)
    bridge = QtControlConfirmation()
    clicked = False
    value = prompt()
    if close:
        value = replace(value, capability=ControlCapability.CLOSE_WINDOW)

    def click() -> None:
        nonlocal clicked
        dialog = bridge._dialog
        if dialog is not None and not clicked:
            clicked = True
            if close:
                text = dialog.findChildren(QLabel)[0].text()
                assert "بستن معمول پنجره" in text and "ذخیره‌نشده" in text
                assert value.window.app_id in text and value.window.window_token in text
            buttons = dialog.findChildren(QPushButton)
            buttons[1 if approve else 0].click()

    assert worker(app, lambda: bridge.confirm(value), click) is approve
    assert clicked and bridge._dialog is None


@pytest.mark.parametrize("stop", ["cancel", "timeout"])
def test_cancelled_or_expired_dialog_cannot_grant_late_consent(stop: str) -> None:
    app = QApplication.instance() or QApplication([])
    assert isinstance(app, QApplication)
    bridge = QtControlConfirmation()
    old_dialogs: list[QDialog] = []

    def work() -> bool:
        with budget(0.08 if stop == "timeout" else 1):
            return bridge.confirm(prompt())

    def invalidate() -> None:
        dialog = bridge._dialog
        if dialog is not None and not old_dialogs:
            old_dialogs.append(dialog)
            if stop == "cancel":
                cancel_operation[0]()
            else:
                # Simulate an affirmative answer after the worker's deadline,
                # before Qt gets its next timer tick to close the old dialog.
                sleep(0.1)
            dialog.findChildren(QPushButton)[1].click()

    cancel_operation: list[Callable[[], None]] = []

    def cancellable_work() -> bool:
        with budget(1) as operation:
            cancel_operation.append(operation.cancel)
            return bridge.confirm(prompt())

    assert not worker(app, cancellable_work if stop == "cancel" else work, invalidate)
    deadline = monotonic() + 0.2
    while bridge._dialog is not None and monotonic() < deadline:
        app.processEvents()
        sleep(0.002)
    assert bridge._dialog is None
    assert old_dialogs


def test_expired_prompt_and_ui_thread_call_cannot_open_dialog() -> None:
    app = QApplication.instance() or QApplication([])
    assert isinstance(app, QApplication)
    bridge = QtControlConfirmation()
    original = prompt()
    expired = replace(
        original,
        window=replace(
            original.window,
            observed_at=original.window.observed_at - 11,
            deadline=original.window.deadline - 11,
        ),
    )
    assert not bridge.confirm(original)
    assert not worker(app, lambda: bridge.confirm(expired), lambda: None)
    assert bridge._dialog is None
