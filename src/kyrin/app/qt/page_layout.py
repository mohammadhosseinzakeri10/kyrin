"""Shared frame for the small settings pages in the control window."""

from collections.abc import Callable

from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget


def settings_page_layout(
    page: QWidget,
    label: Callable[[str], QLabel],
    heading: str,
    caption: str,
) -> QVBoxLayout:
    layout = QVBoxLayout(page)
    layout.setContentsMargins(20, 25, 20, 20)
    title = label(heading)
    title.setObjectName("PageTitle")
    layout.addWidget(title)
    layout.addWidget(label(caption))
    layout.addSpacing(24)
    return layout
