"""Persistent consent shared by admission, executors and future capabilities.

Consent never supplies a target or overrides backend availability. The immutable
snapshot belongs to one session; settings changes stop that session before save.
"""

from dataclasses import dataclass, replace

from kyrin.app.app_permissions import AppPickerCatalog, app_choices
from kyrin.app.settings import AppSettings
from kyrin.commands.models import CommandIntent, CommandKind


@dataclass(frozen=True, slots=True)
class Capability:
    identifier: str
    english: str
    persian: str
    kinds: frozenset[CommandKind] = frozenset()


# New capabilities register here and declare their command kinds. They appear in
# Desktop Actions automatically, use saved capability_grants, and inherit trust.
# The first seven retain the existing, more specific settings editors/scopes.
CAPABILITIES = (
    Capability(
        "open_app",
        "Open applications",
        "بازکردن برنامه‌ها",
        frozenset(
            {
                CommandKind.OPEN_APP,
                CommandKind.NEW_APP_WINDOW,
                CommandKind.NEW_APP_TAB,
                CommandKind.APP_PREFERENCES,
            }
        ),
    ),
    Capability(
        "window_control",
        "Control windows",
        "کنترل پنجره‌ها",
        frozenset(
            {
                CommandKind.RESTORE_APP,
                CommandKind.MINIMIZE_APP,
                CommandKind.MAXIMIZE_APP,
                CommandKind.UNMAXIMIZE_APP,
                CommandKind.FULLSCREEN_APP,
                CommandKind.UNFULLSCREEN_APP,
                CommandKind.SHOW_ALL_WINDOWS,
                CommandKind.SHOW_APP_WINDOWS,
                CommandKind.SELECT_APP_WINDOW,
                CommandKind.HIDE_APP_WINDOWS,
                CommandKind.SELECT_OPEN_APP_WINDOW,
            }
        ),
    ),
    Capability(
        "close_window",
        "Close windows",
        "بستن پنجره‌ها",
        frozenset(
            {
                CommandKind.CLOSE_APP_WINDOW,
                CommandKind.CLOSE_SHOWN_WINDOW,
            }
        ),
    ),
    Capability(
        "telegram_chat",
        "Navigate Telegram",
        "پیمایش تلگرام",
        frozenset(
            {
                CommandKind.OPEN_CHAT,
                CommandKind.TELEGRAM_VIEW,
                CommandKind.TELEGRAM_SETTINGS,
                CommandKind.TELEGRAM_SEARCH_FOCUS,
                CommandKind.TELEGRAM_SEARCH,
            }
        ),
    ),
    Capability(
        "desktop_scroll",
        "Scroll",
        "اسکرول",
        frozenset(
            {
                CommandKind.SCROLL_UP,
                CommandKind.SCROLL_DOWN,
            }
        ),
    ),
    Capability(
        "desktop_control",
        "Click and set controls",
        "کلیک و تغییر کنترل‌ها",
        frozenset({CommandKind.VISIBLE_CONTROL}),
    ),
    Capability("system_power", "System power", "کنترل توان سیستم"),
)
LEGACY_CAPABILITIES = frozenset(
    {
        "open_app",
        "window_control",
        "close_window",
        "telegram_chat",
        "desktop_scroll",
        "desktop_control",
        "system_power",
    }
)


@dataclass(frozen=True, slots=True)
class PermissionPolicy:
    settings: AppSettings
    capabilities: tuple[Capability, ...] = CAPABILITIES

    def allows(self, capability: str, target: str | None = None) -> bool:
        return self.settings.action_execution_enabled and self.has_grant(
            capability, target
        )

    def has_grant(self, capability: str, target: str | None = None) -> bool:
        """Saved selection, also usable for explicit OS setup while actions are off."""
        settings = self.settings
        if capability not in {item.identifier for item in self.capabilities}:
            return False
        if settings.trust_all_capabilities:
            return True
        scopes = {
            "open_app": tuple(app.app_id for app in settings.allowed_apps),
            "window_control": settings.allowed_window_apps,
            "close_window": settings.allowed_close_apps,
            "telegram_chat": settings.allowed_chat_apps,
        }
        if capability in scopes:
            return (
                bool(scopes[capability])
                if target is None
                else target in scopes[capability]
            )
        switches = {
            "desktop_scroll": settings.allow_desktop_scroll,
            "desktop_control": settings.allow_desktop_control,
            "system_power": settings.system_power_enabled,
        }
        return switches.get(capability, capability in settings.capability_grants)

    def allows_intent(self, intent: CommandIntent) -> bool:
        capability = next(
            (
                item.identifier
                for item in self.capabilities
                if intent.kind in item.kinds
            ),
            None,
        )
        if capability is None:
            return False
        target: str | None = intent.target
        if capability == "telegram_chat":
            target = intent.app if intent.kind is CommandKind.OPEN_CHAT else "telegram"
        elif target == "desktop":
            target = None
        if intent.kind is CommandKind.CLOSE_SHOWN_WINDOW:
            if not self.allows("window_control", target):
                return False
            if target is None and not self.settings.trust_all_capabilities:
                return bool(
                    set(self.settings.allowed_close_apps)
                    & set(self.settings.allowed_window_apps)
                )
        return self.allows(capability, target)

    def effective_settings(self, catalog: AppPickerCatalog) -> AppSettings:
        """Expand registered app bindings for composition, never persist expansion.

        Revoking trust restores the user's granular selections. Future installed
        applications are rediscovered on session start under the same trust rule.
        """
        if not (
            self.settings.action_execution_enabled
            and self.settings.trust_all_capabilities
        ):
            return self.settings
        apps = tuple(
            choice.binding
            for choice in app_choices(catalog, self.settings.allowed_apps)
            if choice.installed
        )
        identifiers = tuple(app.app_id for app in apps)
        return replace(
            self.settings,
            allowed_apps=apps,
            allowed_window_apps=identifiers,
            allowed_close_apps=identifiers,
            allowed_chat_apps=("telegram",) if "telegram" in identifiers else (),
            remember_telegram_pointer="telegram" in identifiers,
            allow_desktop_scroll=True,
            allow_desktop_control=True,
            system_power_enabled=True,
        )
