"""Explicit, paged review of locally archived speech transcripts."""

import sqlite3
from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from kyrin.memory.history import ArchivedTurn, SqliteConversationHistory


class ArchivedMemoryDialog(QDialog):
    def __init__(
        self, path: Path, text: Callable[[str], str], parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self._text = text
        self._history = SqliteConversationHistory(path)
        self._turns: dict[int, ArchivedTurn] = {}
        self._oldest_id: int | None = None
        self.setWindowTitle(text("conversation_memory_review_title"))
        self.setMinimumSize(620, 460)
        layout = QVBoxLayout(self)
        self.count_label = QLabel()
        layout.addWidget(self.count_label)
        self.turn_list = QListWidget()
        self.turn_list.currentItemChanged.connect(self._show_selected)
        layout.addWidget(self.turn_list)
        self.preview = QTextEdit()
        self.preview.setReadOnly(True)
        self.preview.setPlaceholderText(text("conversation_memory_select"))
        layout.addWidget(self.preview)
        controls = QHBoxLayout()
        self.older_button = QPushButton(text("conversation_memory_older"))
        self.older_button.clicked.connect(self._load_page)
        controls.addWidget(self.older_button)
        self.restore_button = QPushButton(text("conversation_memory_restore"))
        self.restore_button.setEnabled(False)
        self.restore_button.clicked.connect(self._restore_selected)
        controls.addWidget(self.restore_button)
        self.close_button = QPushButton(text("conversation_memory_close"))
        self.close_button.clicked.connect(self.close)
        controls.addWidget(self.close_button)
        layout.addLayout(controls)
        self._load_page()

    def _load_page(self) -> None:
        page = self._history.archived_page(before_id=self._oldest_id)
        for turn in page:
            self._turns[turn.id] = turn
            item = QListWidgetItem(
                f"{turn.recorded_at:%Y-%m-%d %H:%M}  ·  {turn.text[:80]}"
            )
            item.setData(Qt.ItemDataRole.UserRole, turn.id)
            self.turn_list.addItem(item)
        if page:
            self._oldest_id = page[-1].id
        self.older_button.setEnabled(len(page) == 50)
        self._refresh_count()

    def _refresh_count(self) -> None:
        self.count_label.setText(
            self._text("conversation_memory_archive_count").format(
                count=self._history.archived_count()
            )
        )

    def _show_selected(self, current: QListWidgetItem | None) -> None:
        turn = (
            self._turns.get(current.data(Qt.ItemDataRole.UserRole)) if current else None
        )
        self.preview.setPlainText(turn.text if turn else "")
        self.restore_button.setEnabled(turn is not None)

    def _restore_selected(self) -> None:
        item = self.turn_list.currentItem()
        if item is None:
            return
        if (
            QMessageBox.question(
                self,
                self._text("conversation_memory_restore_title"),
                self._text("conversation_memory_restore_question"),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            != QMessageBox.StandardButton.Yes
        ):
            return
        turn_id = item.data(Qt.ItemDataRole.UserRole)
        try:
            restored = self._history.restore_archived_turn(turn_id)
        except ValueError, sqlite3.Error:
            QMessageBox.warning(
                self, self.windowTitle(), self._text("conversation_memory_unavailable")
            )
            return
        if restored:
            self._turns.pop(turn_id, None)
            self.turn_list.takeItem(self.turn_list.row(item))
            self.preview.clear()
            self.restore_button.setEnabled(False)
            self._refresh_count()

    def closeEvent(self, event: QCloseEvent) -> None:
        self._history.close()
        super().closeEvent(event)
