"""Low-cost dashboard artwork; audio work remains independent of the UI."""

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import (
    QColor,
    QLinearGradient,
    QPainter,
    QPaintEvent,
    QPixmap,
    QResizeEvent,
)
from PySide6.QtWidgets import QLabel

ARTWORK = Path(__file__).with_name("assets") / "cosmic_fallback.png"


class CosmicDashboard(QLabel):
    """Show one still image behind the dashboard text without frame rendering."""

    def __init__(self) -> None:
        super().__init__()
        self._source = QPixmap(str(ARTWORK))
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setAccessibleName("Cosmic dashboard artwork")

    def resizeEvent(self, event: QResizeEvent) -> None:
        if not self._source.isNull() and self.width() > 0 and self.height() > 0:
            scaled = self._source.scaled(
                self.size(),
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation,
            )
            # The chosen artwork places its black hole on the left. Keep that
            # focal point visible when the dashboard panel is narrower.
            x = 0
            y = max(0, (scaled.height() - self.height()) // 2)
            self.setPixmap(scaled.copy(x, y, self.width(), self.height()))
        super().resizeEvent(event)

    def paintEvent(self, event: QPaintEvent) -> None:
        super().paintEvent(event)
        gradient = QLinearGradient(self.width() * 0.48, 0, self.width(), 0)
        gradient.setColorAt(0, QColor(5, 7, 19, 0))
        gradient.setColorAt(1, QColor(5, 7, 19, 170))
        painter = QPainter(self)
        painter.fillRect(self.rect(), gradient)
