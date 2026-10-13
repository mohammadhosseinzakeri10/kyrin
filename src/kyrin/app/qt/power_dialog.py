"""Top-level confirmation surface for a pending system power request."""

from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtGui import QCloseEvent, QCursor
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
)

from kyrin.system_power.flow import PowerAction, PowerPrompt, PowerStage

_ACTION_LABELS = {
    PowerAction.POWER_OFF: "Power off computer",
    PowerAction.RESTART: "Restart computer",
    PowerAction.LOG_OUT: "Log out of session",
    PowerAction.SUSPEND: "Suspend computer",
}


class PowerConfirmationDialog(QDialog):
    """Show the active challenge without exposing a second action path."""

    def __init__(
        self,
        confirm: Callable[[int, str], object],
        cancel: Callable[[int], object],
    ) -> None:
        super().__init__(None)
        self._confirm = confirm
        self._cancel = cancel
        self._prompt: PowerPrompt | None = None
        self.setObjectName("PowerConfirmationDialog")
        self.setWindowTitle("KYRIN — System action confirmation")
        self.setWindowFlags(
            Qt.WindowType.Dialog | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setWindowModality(Qt.WindowModality.NonModal)
        self.setMinimumWidth(420)
        self.setStyleSheet("""
            QDialog#PowerConfirmationDialog { background: #0d1225; }
            QLabel { color: #eef1ff; font-size: 15px; }
            QLabel#PowerActionTitle { color: #d7c9ff; font-size: 20px;
                                      font-weight: 700; }
            QPushButton { background: #293666; color: #f7f3ff;
                          border: 1px solid #8d73ff; border-radius: 8px;
                          padding: 10px 16px; }
            QPushButton:disabled { color: #8a90a8; background: #242a40; }
        """)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 20)
        layout.setSpacing(16)
        self.action_label = QLabel()
        self.action_label.setObjectName("PowerActionTitle")
        layout.addWidget(self.action_label)
        self.message = QLabel()
        self.message.setObjectName("PowerConfirmationMessage")
        self.message.setTextFormat(Qt.TextFormat.PlainText)
        self.message.setWordWrap(True)
        layout.addWidget(self.message)
        self.voice_warning = QLabel()
        self.voice_warning.setObjectName("PowerVoiceWarning")
        self.voice_warning.setWordWrap(True)
        self.voice_warning.setStyleSheet("color: #ffbf79;")
        self.voice_warning.hide()
        layout.addWidget(self.voice_warning)
        buttons = QHBoxLayout()
        buttons.addStretch()
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self._cancel_current)
        buttons.addWidget(self.cancel_button)
        self.confirm_button = QPushButton()
        self.confirm_button.clicked.connect(self._confirm_current)
        buttons.addWidget(self.confirm_button)
        layout.addLayout(buttons)

    def present(self, prompt: PowerPrompt, *, continue_label: str) -> None:
        if prompt.stage not in (
            PowerStage.CHECKING, PowerStage.FIRST, PowerStage.SECOND
        ):
            self.dismiss()
            return
        self._prompt = prompt
        self.action_label.setText(
            ("SAFE PREVIEW · " if prompt.preview else "")
            + _ACTION_LABELS[prompt.action]
        )
        self.message.setText(prompt.text)
        self.voice_warning.hide()
        self.confirm_button.setText(
            continue_label if prompt.stage is PowerStage.FIRST else prompt.phrase or ""
        )
        self.confirm_button.setVisible(prompt.stage is not PowerStage.CHECKING)
        self.confirm_button.setEnabled(prompt.stage is not PowerStage.CHECKING)
        self.adjustSize()
        screen = QApplication.screenAt(QCursor.pos()) or QApplication.primaryScreen()
        if screen is not None:
            area = screen.availableGeometry()
            self.move(area.center() - self.rect().center())
        self.show()
        self.raise_()
        self.activateWindow()

    def dismiss(self) -> None:
        self._prompt = None
        self.hide()

    def show_voice_error(self) -> None:
        if self._prompt is None:
            return
        self.voice_warning.setText(
            "Voice playback is unavailable. Use the buttons or speak your response."
        )
        self.voice_warning.show()
        self.adjustSize()

    def _confirm_current(self) -> None:
        prompt = self._prompt
        if prompt is None or prompt.stage is PowerStage.CHECKING:
            return
        self.confirm_button.setEnabled(False)
        answer = "continue" if prompt.stage is PowerStage.FIRST else prompt.phrase
        if answer is not None:
            self._confirm(prompt.request_id, answer)

    def _cancel_current(self) -> None:
        prompt = self._prompt
        if prompt is not None:
            self._cancel(prompt.request_id)

    def closeEvent(self, event: QCloseEvent) -> None:
        self._cancel_current()
        self._prompt = None
        event.accept()
