"""Operation-specific mascot captions, independent of rendering and execution."""

from kyrin.commands.models import CommandIntent, CommandKind
from kyrin.commands.telegram_settings import SETTING_SECTIONS

# Each operation has an explicit label and an in-progress English form.
# Persian labels are infinitives so the same label also gives result context.
_ACTIONS: dict[CommandKind, tuple[str, str, str]] = {
    CommandKind.OPEN_APP: (
        "بازکردن یا جلوآوردن {target}",
        "Open or activate {target}",
        "Opening or bringing {target} forward",
    ),
    CommandKind.OPEN_CHAT: (
        "بازکردن چت {target}",
        "Open chat {target}",
        "Opening chat {target}",
    ),
    CommandKind.TELEGRAM_VIEW: (
        "بازکردن {target} در تلگرام",
        "Open Telegram {target}",
        "Opening Telegram {target}",
    ),
    CommandKind.TELEGRAM_SETTINGS: (
        "بازکردن تنظیم {target} در تلگرام",
        "Open Telegram setting {target}",
        "Opening Telegram setting {target}",
    ),
    CommandKind.TELEGRAM_SEARCH_FOCUS: (
        "فعال‌کردن جست‌وجوی تلگرام",
        "Focus Telegram search",
        "Focusing Telegram search",
    ),
    CommandKind.TELEGRAM_SEARCH: (
        "جست‌وجوی {target} در تلگرام",
        "Search Telegram for {target}",
        "Searching Telegram for {target}",
    ),
    CommandKind.SCROLL_UP: ("اسکرول به بالا", "Scroll up", "Scrolling up"),
    CommandKind.SCROLL_DOWN: ("اسکرول به پایین", "Scroll down", "Scrolling down"),
    CommandKind.VISIBLE_CONTROL: (
        "فعال‌کردن گزینهٔ {target}",
        "Activate control {target}",
        "Activating control {target}",
    ),
    CommandKind.RESTORE_APP: (
        "جلوآوردن {target}",
        "Bring {target} forward",
        "Bringing {target} forward",
    ),
    CommandKind.MINIMIZE_APP: (
        "کوچک‌کردن {target}",
        "Minimize {target}",
        "Minimizing {target}",
    ),
    CommandKind.CLOSE_APP_WINDOW: (
        "بستن پنجرهٔ {target}",
        "Close a window of {target}",
        "Closing a window of {target}",
    ),
    CommandKind.CLOSE_ALL_APP_WINDOWS: (
        "بستن همهٔ پنجره‌های {target}",
        "Close all windows of {target}",
        "Closing all windows of {target}",
    ),
    CommandKind.MAXIMIZE_APP: (
        "بزرگ‌کردن {target}",
        "Maximize {target}",
        "Maximizing {target}",
    ),
    CommandKind.UNMAXIMIZE_APP: (
        "بازگرداندن اندازهٔ عادی {target}",
        "Restore normal size of {target}",
        "Restoring normal size of {target}",
    ),
    CommandKind.FULLSCREEN_APP: (
        "تمام‌صفحه‌کردن {target}",
        "Make {target} full screen",
        "Making {target} full screen",
    ),
    CommandKind.UNFULLSCREEN_APP: (
        "خروج {target} از حالت تمام‌صفحه",
        "Leave full screen in {target}",
        "Leaving full screen in {target}",
    ),
    CommandKind.NEW_APP_WINDOW: (
        "بازکردن پنجرهٔ تازهٔ {target}",
        "Open a new window of {target}",
        "Opening a new window of {target}",
    ),
    CommandKind.NEW_APP_TAB: (
        "بازکردن زبانهٔ تازهٔ {target}",
        "Open a new tab in {target}",
        "Opening a new tab in {target}",
    ),
    CommandKind.APP_PREFERENCES: (
        "بازکردن تنظیمات {target}",
        "Open preferences for {target}",
        "Opening preferences for {target}",
    ),
    CommandKind.SHOW_ALL_WINDOWS: (
        "نمایش پنجره‌های باز",
        "Show open application windows",
        "Showing open application windows",
    ),
    CommandKind.SHOW_APP_WINDOWS: (
        "نمایش پنجره‌های {target}",
        "Show windows of {target}",
        "Showing windows of {target}",
    ),
    CommandKind.SELECT_APP_WINDOW: (
        "انتخاب پنجرهٔ {number} از {target}",
        "Select window {number} of {target}",
        "Selecting window {number} of {target}",
    ),
    CommandKind.CLOSE_SHOWN_WINDOW: (
        "بستن پنجرهٔ {number} از {target}",
        "Close window {number} of {target}",
        "Closing window {number} of {target}",
    ),
    CommandKind.HIDE_APP_WINDOWS: (
        "بستن پیش‌نمایش پنجره‌ها",
        "Hide window previews",
        "Hiding window previews",
    ),
    CommandKind.SELECT_OPEN_APP_WINDOW: (
        "انتخاب پنجرهٔ بازِ {target}",
        "Select an open window of {target}",
        "Selecting an open window of {target}",
    ),
}

_TELEGRAM_VIEWS = {
    "archive": ("بایگانی", "archive"),
    "contacts": ("مخاطبان", "contacts"),
    "settings": ("تنظیمات", "settings"),
    "profile": ("نمایه", "profile"),
    "calls": ("تماس‌ها", "calls"),
    "new_group": ("گروه تازه", "new group"),
    "new_channel": ("کانال تازه", "new channel"),
}


def action_caption(
    intent: CommandIntent, language: str, *, running: bool = False
) -> str:
    """Describe the actual operation; never fall back to an unrelated open verb."""
    persian = language == "fa"
    fa, en, progress = _ACTIONS[intent.kind]
    target = intent.target
    if intent.kind is CommandKind.TELEGRAM_VIEW:
        target = _TELEGRAM_VIEWS[target][not persian]
    elif intent.kind is CommandKind.TELEGRAM_SETTINGS:
        if target in {"back", "cancel"}:
            fa, en, progress = (
                (
                    "بازگشت از تنظیمات تلگرام",
                    "Go back in Telegram settings",
                    "Going back in Telegram settings",
                )
                if target == "back"
                else (
                    "لغو پیمایش تنظیمات تلگرام",
                    "Cancel Telegram settings navigation",
                    "Cancelling Telegram settings navigation",
                )
            )
        target = SETTING_SECTIONS.get(
            target,
            target.removeprefix("label:").removeprefix("visible:").replace("_", " "),
        )
    elif (
        intent.kind is CommandKind.VISIBLE_CONTROL and intent.control_state is not None
    ):
        fa = ("روشن‌کردن" if intent.control_state else "خاموش‌کردن") + " گزینهٔ {target}"
        en = ("Enable" if intent.control_state else "Disable") + " control {target}"
        progress = (
            "Enabling" if intent.control_state else "Disabling"
        ) + " control {target}"
    value = (fa if persian else progress if running else en).format(
        target=target,
        number=intent.window_index or "",
    )
    if running:
        return ("در حال " if persian else "") + value + "…"
    return value
