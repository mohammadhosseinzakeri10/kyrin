"""Desktop action permissions editor; UI choices never launch an app."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from kyrin.app.app_permissions import AppChoice, AppPickerCatalog, app_choices
from kyrin.app.qt.translations import UiTranslations
from kyrin.app.settings import AllowedApp, AppSettings, AppSpokenAliases
from kyrin.system_power.flow import PowerAction


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
        page_layout = QVBoxLayout(self)
        page_layout.setContentsMargins(0, 0, 0, 0)
        self.scroll_area = QScrollArea()
        self.scroll_area.setObjectName("ActionsScrollArea")
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        page_layout.addWidget(self.scroll_area)
        content = QWidget()
        content.setObjectName("ActionsScrollContent")
        self.scroll_area.setWidget(content)
        layout = QVBoxLayout(content)
        layout.setContentsMargins(20, 25, 20, 20)
        self.heading = QLabel()
        self.heading.setObjectName("PageTitle")
        layout.addWidget(self.heading)
        self.caption = QLabel()
        self.caption.setWordWrap(True)
        layout.addWidget(self.caption)
        layout.addSpacing(24)
        self.enabled_checkbox = QCheckBox()
        layout.addWidget(self.enabled_checkbox)
        self.search = QLineEdit()
        self.search.textChanged.connect(self._filter)
        layout.addWidget(self.search)
        selection_row = QHBoxLayout()
        self.select_visible_button = QPushButton()
        self.select_visible_button.clicked.connect(
            lambda: self._set_visible_check_state(Qt.CheckState.Checked)
        )
        selection_row.addWidget(self.select_visible_button)
        self.clear_visible_button = QPushButton()
        self.clear_visible_button.clicked.connect(
            lambda: self._set_visible_check_state(Qt.CheckState.Unchecked)
        )
        selection_row.addWidget(self.clear_visible_button)
        self.selection_count = QLabel()
        selection_row.addWidget(self.selection_count)
        selection_row.addStretch()
        layout.addLayout(selection_row)
        self.apps = QListWidget()
        self.apps.setAccessibleName("Allowed desktop applications")
        self.apps.setMinimumHeight(300)
        self._pressed_item: QListWidgetItem | None = None
        self._pressed_check_state: Qt.CheckState | None = None
        self.apps.itemPressed.connect(self._remember_pressed_state)
        self.apps.itemClicked.connect(self._toggle_row_if_needed)
        self.apps.itemChanged.connect(self._update_selection_count)
        layout.addWidget(self.apps)
        self.aliases_label = QLabel()
        layout.addWidget(self.aliases_label)
        self.aliases_edit = QLineEdit()
        self.aliases_edit.setAccessibleName("Spoken names for selected application")
        self._aliases_by_platform_id = {
            item.platform_id: item.aliases
            for item in (settings.app_spoken_aliases if settings is not None else ())
        }
        self.aliases_edit.textChanged.connect(self._remember_aliases)
        self.apps.itemSelectionChanged.connect(self._show_aliases)
        layout.addWidget(self.aliases_edit)
        self.aliases_help = QLabel()
        self.aliases_help.setWordWrap(True)
        layout.addWidget(self.aliases_help)
        self.telegram_chat_checkbox = QCheckBox()
        layout.addWidget(self.telegram_chat_checkbox)
        self.window_control_checkbox = QCheckBox()
        layout.addWidget(self.window_control_checkbox)
        self.close_window_checkbox = QCheckBox()
        layout.addWidget(self.close_window_checkbox)
        self.system_power_checkbox = QCheckBox()
        layout.addWidget(self.system_power_checkbox)
        self.power_buttons: dict[PowerAction, QPushButton] = {}
        power_row = QHBoxLayout()
        for action in PowerAction:
            button = QPushButton()
            self.power_buttons[action] = button
            power_row.addWidget(button)
        layout.addLayout(power_row)
        self.power_preview_button = QPushButton()
        layout.addWidget(self.power_preview_button)

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
            self.telegram_chat_checkbox.setChecked(
                "telegram" in settings.allowed_chat_apps
            )
            selected_app_ids = {binding.app_id for binding in settings.allowed_apps}
            self.window_control_checkbox.setChecked(
                bool(selected_app_ids)
                and selected_app_ids == set(settings.allowed_window_apps)
            )
            self.close_window_checkbox.setChecked(
                bool(selected_app_ids)
                and selected_app_ids == set(settings.allowed_close_apps)
            )
            self.system_power_checkbox.setChecked(settings.system_power_enabled)
        else:
            self.enabled_checkbox.setEnabled(False)
            self.apps.setEnabled(False)
            self.select_visible_button.setEnabled(False)
            self.clear_visible_button.setEnabled(False)
            self.telegram_chat_checkbox.setEnabled(False)
            self.window_control_checkbox.setEnabled(False)
            self.close_window_checkbox.setEnabled(False)
            self.system_power_checkbox.setEnabled(False)
            self.power_preview_button.setEnabled(False)
        self.translate()
        self._show_aliases()
        self._update_chat_permission_availability()

    def _current_app_choice(self) -> AppChoice | None:
        item = self.apps.currentItem()
        if item is None:
            return None
        choice = item.data(Qt.ItemDataRole.UserRole)
        return choice if isinstance(choice, AppChoice) else None

    def _show_aliases(self) -> None:
        choice = self._current_app_choice()
        self.aliases_edit.setEnabled(choice is not None)
        self.aliases_edit.blockSignals(True)
        self.aliases_edit.setText(
            ", ".join(self._aliases_by_platform_id.get(choice.binding.desktop_id, ()))
            if choice is not None
            else ""
        )
        self.aliases_edit.blockSignals(False)

    def _remember_aliases(self, _text: str) -> None:
        choice = self._current_app_choice()
        if choice is None:
            return
        aliases = tuple(
            alias.strip()
            for alias in self.aliases_edit.text().split(",")
            if alias.strip()
        )
        if aliases:
            self._aliases_by_platform_id[choice.binding.desktop_id] = aliases
        else:
            self._aliases_by_platform_id.pop(choice.binding.desktop_id, None)

    def _remember_pressed_state(self, item: QListWidgetItem) -> None:
        self._pressed_item = item
        self._pressed_check_state = item.checkState()

    def _toggle_row_if_needed(self, item: QListWidgetItem) -> None:
        # Qt already toggles a click on the indicator. A click elsewhere in
        # the row leaves the state unchanged, so toggle only in that case.
        if (
            item is self._pressed_item
            and item.checkState() == self._pressed_check_state
        ):
            item.setCheckState(
                Qt.CheckState.Unchecked
                if item.checkState() is Qt.CheckState.Checked
                else Qt.CheckState.Checked
            )
        self._pressed_item = None
        self._pressed_check_state = None

    def _set_visible_check_state(self, state: Qt.CheckState) -> None:
        for index in range(self.apps.count()):
            item = self.apps.item(index)
            if item is None or item.isHidden():
                continue
            choice = item.data(Qt.ItemDataRole.UserRole)
            if isinstance(choice, AppChoice) and (
                choice.installed or state is Qt.CheckState.Unchecked
            ):
                item.setCheckState(state)

    def _update_selection_count(self, item: QListWidgetItem | None = None) -> None:
        self.selection_count.setText(
            f"{len(self.selected_apps())} {self._translations.text('actions_selected')}"
        )
        self._update_chat_permission_availability()

    def _update_chat_permission_availability(self) -> None:
        telegram_selected = any(
            app.app_id == "telegram" for app in self.selected_apps()
        )
        self.telegram_chat_checkbox.setEnabled(telegram_selected)
        if not telegram_selected:
            self.telegram_chat_checkbox.setChecked(False)

    def translate(self) -> None:
        text = self._translations.text
        self.heading.setText(text("actions_heading"))
        self.caption.setText(text("actions_caption"))
        self.enabled_checkbox.setText(text("enable_actions"))
        self.telegram_chat_checkbox.setText(text("allow_telegram_chats"))
        self.window_control_checkbox.setText(text("allow_window_controls"))
        self.close_window_checkbox.setText(text("allow_window_close"))
        self.system_power_checkbox.setText(text("allow_system_power"))
        self.power_preview_button.setText(text("power_safe_preview"))
        self.search.setPlaceholderText(text("actions_search"))
        self.aliases_label.setText(text("app_spoken_aliases"))
        self.aliases_edit.setPlaceholderText(text("app_spoken_aliases_placeholder"))
        self.aliases_help.setText(text("app_spoken_aliases_help"))
        self.select_visible_button.setText(text("actions_select_visible"))
        self.clear_visible_button.setText(text("actions_clear_visible"))
        for action, key in (
            (PowerAction.POWER_OFF, "power_off_button"),
            (PowerAction.RESTART, "restart_button"),
            (PowerAction.LOG_OUT, "log_out_button"),
            (PowerAction.SUSPEND, "suspend_button"),
        ):
            self.power_buttons[action].setText(text(key))
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
        self._update_selection_count()

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

    def selected_spoken_aliases(self) -> tuple[AppSpokenAliases, ...]:
        return tuple(
            AppSpokenAliases(platform_id, aliases)
            for platform_id, aliases in sorted(self._aliases_by_platform_id.items())
        )

    def selected_chat_apps(self) -> tuple[str, ...]:
        return ("telegram",) if self.telegram_chat_checkbox.isChecked() else ()

    def selected_window_apps(self) -> tuple[str, ...]:
        return (
            tuple(app.app_id for app in self.selected_apps())
            if self.window_control_checkbox.isChecked()
            else ()
        )

    def selected_close_apps(self) -> tuple[str, ...]:
        return (
            tuple(app.app_id for app in self.selected_apps())
            if self.close_window_checkbox.isChecked()
            else ()
        )

    def has_unsaved_changes(self, settings: AppSettings) -> bool:
        return (
            self.enabled_checkbox.isChecked() != settings.action_execution_enabled
            or set(self.selected_apps()) != set(settings.allowed_apps)
            or self.selected_chat_apps() != settings.allowed_chat_apps
            or set(self.selected_window_apps()) != set(settings.allowed_window_apps)
            or set(self.selected_close_apps()) != set(settings.allowed_close_apps)
            or self.system_power_checkbox.isChecked() != settings.system_power_enabled
            or self._aliases_by_platform_id
            != {item.platform_id: item.aliases for item in settings.app_spoken_aliases}
        )
