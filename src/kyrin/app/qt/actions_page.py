"""Desktop action permissions editor; UI choices never launch an app."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
    QWidget,
)

from kyrin.app.app_permissions import AppChoice, AppPickerCatalog, app_choices
from kyrin.app.qt.translations import UiTranslations
from kyrin.app.settings import AllowedApp, AppSettings


class DesktopActionsPage(QWidget):
    """Edit an allowlist by registered desktop ID, independent of audio work."""

    def __init__(
        self,
        catalog: AppPickerCatalog | None,
        settings: AppSettings | None,
        translations: UiTranslations,
    ) -> None:
        super().__init__()
        self._translations = translations
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 25, 20, 20)
        self.heading = QLabel()
        self.heading.setObjectName("PageTitle")
        layout.addWidget(self.heading)
        self.caption = QLabel()
        layout.addWidget(self.caption)
        layout.addSpacing(24)
        self.enabled_checkbox = QCheckBox()
        layout.addWidget(self.enabled_checkbox)
        self.search = QLineEdit()
        self.search.textChanged.connect(self._filter)
        layout.addWidget(self.search)
        self.apps = QListWidget()
        self.apps.setAccessibleName("Allowed desktop applications")
        layout.addWidget(self.apps, 1)

        if settings is not None:
            self.enabled_checkbox.setChecked(settings.action_execution_enabled)
            if catalog is not None:
                choices = app_choices(catalog, settings.allowed_apps)
            else:
                choices = tuple(
                    AppChoice(binding, binding.desktop_id, False)
                    for binding in settings.allowed_apps
                )
            selected_ids = {binding.desktop_id for binding in settings.allowed_apps}
            for choice in choices:
                item = QListWidgetItem()
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                item.setData(Qt.ItemDataRole.UserRole, choice)
                item.setCheckState(
                    Qt.CheckState.Checked
                    if choice.binding.desktop_id in selected_ids
                    else Qt.CheckState.Unchecked
                )
                self.apps.addItem(item)
        else:
            self.enabled_checkbox.setEnabled(False)
            self.apps.setEnabled(False)
        self.translate()

    def translate(self) -> None:
        text = self._translations.text
        self.heading.setText(text("actions_heading"))
        self.caption.setText(text("actions_caption"))
        self.enabled_checkbox.setText(text("enable_actions"))
        self.search.setPlaceholderText(text("actions_search"))
        for index in range(self.apps.count()):
            item = self.apps.item(index)
            if item is None:
                continue
            choice = item.data(Qt.ItemDataRole.UserRole)
            if not isinstance(choice, AppChoice):
                continue
            suffix = "" if choice.installed else f" · {text('app_unavailable')}"
            item.setText(f"{choice.display_name} · {choice.binding.desktop_id}{suffix}")
        self._filter(self.search.text())

    def _filter(self, query: str) -> None:
        needle = query.casefold().strip()
        for index in range(self.apps.count()):
            item = self.apps.item(index)
            if item is not None:
                item.setHidden(needle not in item.text().casefold())

    def selected_apps(self) -> tuple[AllowedApp, ...]:
        bindings: list[AllowedApp] = []
        for index in range(self.apps.count()):
            item = self.apps.item(index)
            if item is not None and item.checkState() is Qt.CheckState.Checked:
                choice = item.data(Qt.ItemDataRole.UserRole)
                if isinstance(choice, AppChoice):
                    bindings.append(choice.binding)
        return tuple(bindings)

    def has_unsaved_changes(self, settings: AppSettings) -> bool:
        return (
            self.enabled_checkbox.isChecked() != settings.action_execution_enabled
            or set(self.selected_apps()) != set(settings.allowed_apps)
        )
