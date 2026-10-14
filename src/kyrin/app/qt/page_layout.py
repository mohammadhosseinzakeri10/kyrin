"""Shared frame for the small settings pages in the control window."""

from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QLabel, QScrollArea, QVBoxLayout, QWidget


def scrollable_page_layout(page: QWidget) -> tuple[QVBoxLayout, QScrollArea]:
    """Keep controls at readable sizes when the control window is short."""
    outer = QVBoxLayout(page)
    outer.setContentsMargins(0, 0, 0, 0)
    scroll = QScrollArea()
    scroll.setObjectName("SettingsScrollArea")
    scroll.setFrameShape(QFrame.Shape.NoFrame)
    scroll.setWidgetResizable(True)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    outer.addWidget(scroll)
    content = QWidget()
    content.setObjectName("SettingsScrollContent")
    scroll.setWidget(content)
    layout = QVBoxLayout(content)
    layout.setContentsMargins(20, 25, 20, 20)
    return layout, scroll


def settings_page_layout(
    page: QWidget,
    label: Callable[[str], QLabel],
    heading: str,
    caption: str,
) -> QVBoxLayout:
    layout, _scroll = scrollable_page_layout(page)
    title = label(heading)
    title.setObjectName("PageTitle")
    layout.addWidget(title)
    description = label(caption)
    description.setWordWrap(True)
    layout.addWidget(description)
    layout.addSpacing(24)
    return layout
