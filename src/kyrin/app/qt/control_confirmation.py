"""Qt-owned consent for one observed control, independent of OCR permissions."""

from dataclasses import dataclass, field
from threading import Event
from time import monotonic

from PySide6.QtCore import QObject, Qt, QThread, QTimer, Signal, Slot
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout

from kyrin.actions.control_policy import ControlCapability, ControlConfirmation
from kyrin.operations import Operation, OperationStopped, budget


@dataclass(slots=True)
class _ConfirmationRequest:
    prompt: ControlConfirmation
    operation: Operation
    finished: Event = field(default_factory=Event)
    approved: bool = False


class QtControlConfirmation(QObject):
    requested = Signal(object)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._dialog: QDialog | None = None
        self.requested.connect(self._show)

    def confirm(self, prompt: ControlConfirmation) -> bool:
        """Only a button in this exact live dialog can approve the worker request."""
        if QThread.currentThread() == self.thread() or not prompt.window.current(
            prompt.window.window_token, monotonic()
        ):
            return False
        request: _ConfirmationRequest | None = None
        try:
            with budget(max(0.001, prompt.window.deadline - monotonic())) as operation:
                request = _ConfirmationRequest(prompt, operation)
                self.requested.emit(request)
                while not request.finished.wait(min(0.02, operation.remaining())):
                    operation.remaining()
                operation.remaining()
                return request.approved
        except OperationStopped:
            if request is not None:
                request.operation.cancel()
            return False

    @Slot(object)
    def _show(self, value: object) -> None:
        if not isinstance(value, _ConfirmationRequest):
            return
        request = value
        if (
            request.operation.stopped
            or self._dialog is not None
            or monotonic() >= request.prompt.window.deadline
        ):
            request.finished.set()
            return
        prompt = request.prompt
        persian = (prompt.language or "").split("-")[0] == "fa"
        dialog = QDialog()
        self._dialog = dialog
        dialog.setWindowTitle(
            "KYRIN — تأیید کنترل" if persian else "KYRIN — Confirm control"
        )
        dialog.setWindowFlags(
            Qt.WindowType.Tool
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.WindowDoesNotAcceptFocus
        )
        dialog.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        dialog.setLayoutDirection(
            Qt.LayoutDirection.RightToLeft
            if persian
            else Qt.LayoutDirection.LeftToRight
        )
        layout = QVBoxLayout(dialog)
        desired = (
            ("بستن معمول پنجره" if persian else "Normal window close")
            if prompt.capability is ControlCapability.CLOSE_WINDOW
            else ("کلیک" if persian else "Activate")
            if prompt.desired_state is None
            else ("روشن" if prompt.desired_state else "خاموش")
            if persian
            else ("On" if prompt.desired_state else "Off")
        )
        consequence = (
            (
                "وضعیت کار ذخیره‌نشده یا فرایند در حال اجرا مشخص نیست. "
                "ممکن است کار از دست برود؛ پرسش ذخیره‌سازی خود برنامه پاسخ داده نمی‌شود."
                if persian
                else "Unsaved work or running jobs may be lost. The application's own "
                "save dialog will not be answered."
            )
            if prompt.capability is ControlCapability.CLOSE_WINDOW
            else (
                "پیامد دقیق این کنترل ناشناخته است."
                if persian
                else "The exact effect of this control is unknown."
            )
        )
        text = (
            f"هدف: {prompt.target.label}\nعمل/وضعیت مطلوب: {desired}\n"
            f"برنامه: {prompt.window.app_id}\nپنجره: {prompt.window.window_token}\n"
            f"{consequence} فقط همین عمل را تأیید می‌کنید؛ "
            "تأیید یک‌بارمصرف است و با پایان مهلت فرمان باطل می‌شود."
            if persian
            else f"Target: {prompt.target.label}\n"
            f"Operation / desired state: {desired}\n"
            f"App: {prompt.window.app_id}\nWindow: {prompt.window.window_token}\n"
            f"{consequence} Approve only this operation, "
            "once, before the command expires."
        )
        message = QLabel(text)
        message.setTextFormat(Qt.TextFormat.PlainText)
        message.setWordWrap(True)
        layout.addWidget(message)
        buttons = QHBoxLayout()
        cancel = QPushButton("لغو" if persian else "Cancel")
        approve = QPushButton("تأیید همین عمل" if persian else "Approve this operation")
        cancel.setAutoDefault(False)
        approve.setAutoDefault(False)
        cancel.clicked.connect(dialog.reject)
        approve.clicked.connect(dialog.accept)
        buttons.addWidget(cancel)
        buttons.addWidget(approve)
        layout.addLayout(buttons)
        timer = QTimer(dialog)

        def finish(result: int) -> None:
            if not request.finished.is_set():
                request.approved = (
                    result == QDialog.DialogCode.Accepted
                    and not request.operation.stopped
                    and monotonic() < prompt.window.deadline
                )
                request.finished.set()
            timer.stop()
            if self._dialog is dialog:
                self._dialog = None
            dialog.deleteLater()

        def poll() -> None:
            if request.operation.stopped or monotonic() >= prompt.window.deadline:
                dialog.reject()

        dialog.finished.connect(finish)
        timer.timeout.connect(poll)
        timer.start(25)
        dialog.show()
