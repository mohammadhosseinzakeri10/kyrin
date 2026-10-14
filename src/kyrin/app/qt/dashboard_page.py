"""Welcome page with the cosmic artwork and translated copy."""

from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from kyrin.app.qt.dashboard import CosmicDashboard


class DashboardPage(QWidget):
    def __init__(self, label: Callable[[str], QLabel]) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.cosmic_dashboard = CosmicDashboard()
        self.cosmic_dashboard.setObjectName("CosmicDashboard")
        self.cosmic_dashboard.setMinimumSize(600, 400)
        self.cosmic_dashboard.setLayoutDirection(Qt.LayoutDirection.LeftToRight)

        hero_layout = QHBoxLayout(self.cosmic_dashboard)
        hero_layout.setContentsMargins(0, 0, 0, 0)
        hero_layout.addStretch(6)
        hero_copy = QWidget(self.cosmic_dashboard)
        hero_copy.setObjectName("HeroCopy")
        hero_copy_layout = QVBoxLayout(hero_copy)
        hero_copy_layout.setContentsMargins(0, 36, 52, 36)
        hero_copy_layout.addStretch()
        self.welcome_label = label("welcome")
        self.welcome_label.setObjectName("Welcome")
        self.welcome_label.setWordWrap(True)
        self.welcome_label.setAlignment(Qt.AlignmentFlag.AlignLeading)
        shadow = QGraphicsDropShadowEffect(self.welcome_label)
        shadow.setBlurRadius(18)
        shadow.setOffset(0, 3)
        shadow.setColor(QColor(1, 3, 13, 230))
        self.welcome_label.setGraphicsEffect(shadow)
        hero_copy_layout.addWidget(self.welcome_label)
        self.welcome_caption_label = label("welcome_caption")
        self.welcome_caption_label.setObjectName("WelcomeCaption")
        self.welcome_caption_label.setWordWrap(True)
        hero_copy_layout.addWidget(self.welcome_caption_label)
        hero_copy_layout.addSpacing(18)
        self.scene_hint_label = label("scene_hint")
        self.scene_hint_label.setObjectName("SceneHint")
        self.scene_hint_label.setWordWrap(True)
        hero_copy_layout.addWidget(self.scene_hint_label)
        hero_copy_layout.addStretch()
        hero_layout.addWidget(hero_copy, 5)
        layout.addWidget(self.cosmic_dashboard, 1)
