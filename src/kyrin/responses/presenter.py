"""Turn command and action events into text without invoking a UI or TTS."""

from dataclasses import dataclass

from kyrin.actions.models import ActionFeedback, ActionNotice, ActionOutcome
from kyrin.commands.models import (
    CommandKind,
    ResponseChannel,
    ResponseKind,
    ResponseRequest,
)
from kyrin.responses.models import SystemNotice

_TEXT: dict[str, dict[str, str]] = {
    "fa": {
        "ready_for_command": "گوش می‌دهم؛ فرمانتان را بگویید.",
        "repeat_command": "متوجه نشدم. لطفاً فرمان را دوباره بگویید.",
        "choose_chat_app": "چت را در کدام برنامه باز کنم؟",
        "choose_chat_app_pair": "چت {target} را در {first} باز کنم یا {second}؟",
        "confirm_app": "منظورتان برنامهٔ {target} است؟",
        "choose_app_or_chat": (
            "منظورتان کدام است؟ ۱. برنامهٔ {target}؛ ۲. چت. "
            "نام گزینه یا شمارهٔ آن را بگویید."
        ),
        "choose_app": "کدام برنامه را می‌خواهید؟ {options} شماره یا نام را بگویید.",
        "choose_app_to_close": (
            "کدام برنامه را ببندم؟ {options} شماره یا نام را بگویید."
        ),
        "choose_operation": (
            "برای {target} چه کنم؟ {options} شماره را بگویید یا «خیر» بگویید."
        ),
        "choose_operation_open": (
            "برای {target} چه کنم؟ {options} برای بازکردن یا جلوآوردن «بله»، "
            "برای لغو «خیر»، یا شمارهٔ گزینه را بگویید."
        ),
        "choose_operation_only_open": (
            "برنامهٔ {target} را باز کنم؟ «بله» یا «خیر» بگویید."
        ),
        "choose_window": (
            "فقط پنجره‌های {target} نمایش داده شده‌اند. "
            "شمارهٔ پنجرهٔ موردنظر را بگویید یا روی آن کلیک کنید."
        ),
        "choose_open_window": (
            "پنجره‌های برنامه‌هایی که برای کنترل آن‌ها اجازه داده‌اید نمایش داده شدند. "
            "شماره را بگویید، روی پیش‌نمایش کلیک کنید، یا نام برنامه را بگویید. "
            "اگر چند پنجره از یک برنامه باز است، شمارهٔ پنجره را بگویید."
        ),
        "confirm_action": "آیا واقعاً می‌خواهید {target} را ببندم؟ بله یا خیر؟",
        "confirm_numbered_close": "پنجرهٔ شمارهٔ {number} را ببندم؟ بله یا خیر؟",
        "choose_app_duplicate": (
            "چند برنامه با نام {target} پیدا شد. لطفاً نام متفاوتی بگویید."
        ),
        "not_allowed": "اجازهٔ انجام این کار را ندارم.",
        "confirmation_required": "برای انجام این کار به تأیید شما نیاز دارم.",
        "busy": "فعلاً مشغولم. لطفاً کمی بعد دوباره تلاش کنید.",
        "cancelled": "انجام این کار لغو شد.",
        "unsupported": "این بخش از فرمان هنوز پشتیبانی نمی‌شود.",
        "unsupported_chat": "هنوز نمی‌توانم چت را باز کنم.",
        "unsupported_chat_target": "نام یا برنامهٔ این چت پشتیبانی نمی‌شود.",
        "chat_search_uncertain": (
            "برای نام «{target}» نتیجهٔ یکتا و دقیق پیدا نکردم؛ "
            "لطفاً نام چت را دوباره بگویید."
        ),
        "visible_chat_uncertain": (
            "چتِ قابل‌دیدن با نام «{target}» را با اطمینان پیدا نکردم. "
            "برای جست‌وجوی همهٔ چت‌ها، «Open chat» را بگویید."
        ),
        "chat_selection_expired": (
            "زمان انتخاب چت تمام شد؛ لطفاً فرمان را دوباره بگویید."
        ),
        "chat_selection_cancelled": "انتخاب چت لغو شد.",
        "telegram_control_setup_required": (
            "برای بازکردن چت، در تنظیمات Desktop Actions دسترسی کنترل Telegram "
            "را فعال و از همان‌جا تأیید کنید."
        ),
        "telegram_control_unavailable": (
            "اتصال کنترل تلگرام برقرار نشد؛ دسترسی Desktop Actions را بررسی کنید."
        ),
        "screen_access_required": "برای بررسی چت، دسترسی صفحه را در برنامه فعال کنید.",
        "telegram_not_active": (
            "تلگرام فعال نیست؛ لطفاً آن را جلو بیاورید و دوباره بگویید."
        ),
        "telegram_focus_changed": "پنجرهٔ فعال تغییر کرد؛ فرمان چت متوقف شد.",
        "chat_target_changed": (
            "جای ردیف چت یا اندازهٔ پنجره تغییر کرد؛ دوباره تلاش کنید."
        ),
        "scroll_focus_changed": "پنجرهٔ فعال تغییر کرد؛ اسکرول متوقف شد.",
        "scroll_control_setup_required": (
            "برای اسکرول، دسترسی آن را در Desktop Actions فعال و تنظیم کنید."
        ),
        "scroll_unavailable": "نتوانستم اسکرول را انجام دهم. لطفاً صفحه را بررسی کنید.",
        "visible_control_uncertain": "گزینهٔ قابل‌دیدنِ یکتایی با این نام پیدا نکردم.",
        "visible_control_capture_geometry_required": (
            "افزونهٔ تصویربرداری اطلاعات مختصات را نمی‌دهد. پس از نصب نسخهٔ جدید، "
            "کارهایتان را ذخیره کنید و یک بار از حساب Ubuntu خارج و دوباره وارد شوید."
        ),
        "visible_control_screen_access_required": (
            "برای دیدن گزینه‌ها، دسترسی صفحه را در Screen Access فعال کنید."
        ),
        "visible_control_focus_changed": "پنجرهٔ فعال تغییر کرد؛ فرمان متوقف شد.",
        "visible_control_target_changed": (
            "جای گزینه یا اندازهٔ پنجره تغییر کرد؛ دوباره تلاش کنید."
        ),
        "visible_control_setup_required": (
            "مجوز سیستم برای کلیک هنوز ذخیره نشده است. در Desktop Actions، "
            "پس از ذخیرهٔ تنظیمات، «تنظیم دسترسی کلیک دسکتاپ» را بزنید و "
            "پنجرهٔ Remote Desktop را یک‌بار تأیید کنید."
        ),
        "visible_control_state_unavailable": (
            "وضعیت این گزینه از رابط دسترس‌پذیری خوانده نشد؛ تغییری ندادم."
        ),
        "visible_control_sensitive": (
            "این پیامد به ابزار و مجوز اختصاصی نیاز دارد؛ "
            "کنترل عمومی آن را اجرا نمی‌کند."
        ),
        "visible_control_capability_required": (
            "ابزار این نوع کنترل را پشتیبانی نمی‌کند."
        ),
        "visible_control_confirmation_declined": (
            "تأیید این عمل دریافت نشد؛ اجرا نشد."
        ),
        "window_close_confirmation_required": (
            "بستن پنجره به تأیید همان پنجره نیاز دارد؛ رابط تأیید در دسترس نیست."
        ),
        "window_close_confirmation_declined": "بستن پنجره تأیید نشد؛ اجرا نشد.",
        "visible_control_confirmation_expired": (
            "تأیید یا پنجرهٔ هدف معتبر نیست؛ فرمان تازه بدهید."
        ),
        "visible_control_risk_unknown": (
            "پیامد این گزینه مشخص نیست و تا فراهم شدن تأیید جداگانه اجرا نمی‌شود."
        ),
        "visible_control_unavailable": (
            "کنترل برنامه در دسترس نبود؛ لطفاً صفحه را بررسی کنید."
        ),
        "scroll_dispatched": "فرمان اسکرول ارسال شد؛ حرکت صفحه را هنوز تأیید نکرده‌ام.",
        "chat_unverified": "بازشدن چت را نتوانستم تأیید کنم. لطفاً صفحه را بررسی کنید.",
        "telegram_menu_uncertain": (
            "گزینهٔ موردنظر را در منوی تلگرام با اطمینان پیدا نکردم."
        ),
        "telegram_setting_not_found": (
            "گزینهٔ تنظیمات را در صفحهٔ فعلی تلگرام با اطمینان پیدا نکردم."
        ),
        "telegram_settings_not_open": (
            "صفحهٔ تنظیمات تلگرام باز نیست؛ ابتدا آن را باز کنید."
        ),
        "telegram_settings_navigation_uncertain": (
            "بازگشت به فهرست تنظیمات تلگرام تأیید نشد؛ فرمان متوقف شد."
        ),
        "telegram_setting_requires_value": (
            "این مورد یک کنترل تنظیمات است، نه صفحهٔ قابل‌بازکردن؛ تغییری اعمال نشد."
        ),
        "telegram_input_unknown": (
            "نتیجهٔ ورودی تلگرام مشخص نیست؛ لطفاً صفحه را بررسی کنید."
        ),
        "telegram_view_dispatched": (
            "فرمان به تلگرام فرستاده شد؛ صفحهٔ مقصد را هنوز تأیید نکرده‌ام."
        ),
        "telegram_search_dispatched": (
            "فرمان جست‌وجو به تلگرام فرستاده شد؛ وضعیت کادر را هنوز تأیید نکرده‌ام."
        ),
        "no_window": "پنجره‌ای از این برنامه پیدا نکردم.",
        "multiple_windows": (
            "این برنامه چند پنجره دارد. پنجرهٔ موردنظر را فعال کنید "
            "و فرمان را دوباره بگویید."
        ),
        "unavailable": "این پنجره از تغییر درخواستی پشتیبانی نمی‌کند.",
        "window_unverified": (
            "نتیجهٔ تغییر پنجره را نتوانستم تأیید کنم. لطفاً صفحه را بررسی کنید."
        ),
        "window_state_changed": (
            "فهرست پنجره‌ها تغییر کرده است. لطفاً دوباره پنجره‌ها را نمایش دهید."
        ),
        "dependency_unverified": (
            "پیش‌نیاز این مرحله تأیید نشد؛ مرحلهٔ وابسته را اجرا نکردم."
        ),
        "confirmed": "انجام شد.",
        "confirmed_active_app": "برنامهٔ موردنظر اکنون فعال است.",
        "launch_accepted": (
            "درخواست انجام کار پذیرفته شد؛ نتیجهٔ آن هنوز تأیید نشده است."
        ),
        "dispatched_unverified": ("ورودی ارسال شد؛ نتیجهٔ کار هنوز تأیید نشده است."),
        "chat_selection_dispatched": (
            "روی نتیجهٔ انتخاب‌شده کلیک شد؛ به‌دلیل عنوان‌های یکسان، "
            "هویت دقیق چت تأیید نشد."
        ),
        "unknown": "نتیجهٔ انجام کار مشخص نیست. لطفاً وضعیت را بررسی کنید.",
        "failed": "نتوانستم این کار را انجام دهم. لطفاً دوباره تلاش کنید.",
        "processing_delayed": "در حال پردازش گفتار قبلی هستم. لطفاً کمی مکث کنید.",
        "processing_ready": "اکنون می‌توانید ادامه دهید.",
        "processing_overloaded": (
            "پردازش صدا عقب افتاد و ممکن است بخشی از گفتار از دست رفته باشد. "
            "لطفاً مکث کنید و دوباره بگویید."
        ),
        "audio_input_failure": "دریافت صدا متوقف شد. لطفاً ورودی صوتی را بررسی کنید.",
        "compute_unavailable": (
            "پردازندهٔ انتخاب‌شده برای تشخیص گفتار در دسترس نیست. "
            "تنظیمات پردازش را بررسی کنید."
        ),
        "model_unavailable": (
            "مدل تشخیص گفتار پیدا نشد. نصب مدل یا مسیر آن را بررسی کنید."
        ),
        "transcription_failure": (
            "تبدیل گفتار به متن دچار مشکل شد. لطفاً دوباره تلاش کنید."
        ),
        "general_failure": "مشکلی پیش آمد. لطفاً دوباره تلاش کنید.",
        "listening_retry": "برای راه‌اندازی دوبارهٔ دریافت گفتار تلاش می‌کنم.",
    },
    "en": {
        "ready_for_command": "I'm listening. Tell me what to do.",
        "repeat_command": "I didn't understand. Please repeat the command.",
        "choose_chat_app": "Which app should I open the chat in?",
        "choose_chat_app_pair": (
            "Should I open {target}'s chat in {first} or {second}?"
        ),
        "confirm_app": "Did you mean the {target} app?",
        "choose_app_or_chat": (
            "Do you mean the {target} app or a chat? "
            "1. App. 2. Chat. Say app, chat, or the option number."
        ),
        "choose_app": "Which app do you mean? {options} Say its number or name.",
        "choose_app_to_close": (
            "Which app should I close? {options} Say its number or name."
        ),
        "choose_operation": (
            "What should I do with {target}? {options} Say a number or no."
        ),
        "choose_operation_open": (
            "What should I do with {target}? {options} Say yes to open or "
            "bring it forward, no to cancel, or choose an option number."
        ),
        "choose_operation_only_open": "Open {target}? Say yes or no.",
        "choose_window": (
            "Only {target} windows are shown. Say a window number or click its preview."
        ),
        "choose_open_window": (
            "Windows of apps you've allowed to be controlled are shown. "
            "Say a number, click a preview, or say an app name. "
            "For multiple windows of the same app, choose a number."
        ),
        "confirm_action": "Do you really want me to close {target}? Yes or no?",
        "confirm_numbered_close": "Close window number {number}? Yes or no?",
        "choose_app_duplicate": (
            "Multiple apps are named {target}. Please use a different name."
        ),
        "not_allowed": "I can't perform that action.",
        "confirmation_required": "Please confirm before I do that.",
        "busy": "I'm still processing. Please wait and try again.",
        "cancelled": "That action was cancelled.",
        "unsupported": "I can't perform this step yet.",
        "unsupported_chat": "I can't open chats yet.",
        "unsupported_chat_target": "That chat name or app is not supported.",
        "chat_search_uncertain": (
            "I couldn't find one exact chat result for “{target}”. "
            "Please repeat the chat name."
        ),
        "visible_chat_uncertain": (
            "I couldn't confidently find “{target}” in the visible chat list. "
            "Say Open chat to search all chats."
        ),
        "chat_selection_expired": "Chat selection expired. Please repeat the command.",
        "chat_selection_cancelled": "Chat selection was cancelled.",
        "telegram_control_setup_required": (
            "Set up Telegram control access in Desktop Actions before opening chats."
        ),
        "telegram_control_unavailable": (
            "Telegram control could not connect. Check Desktop Actions access."
        ),
        "screen_access_required": "Enable Screen Access in KYRIN to verify the chat.",
        "telegram_not_active": (
            "Telegram is not active. Bring it forward and try again."
        ),
        "telegram_focus_changed": (
            "The active window changed, so I stopped the chat command."
        ),
        "chat_target_changed": (
            "The chat row or window changed before the click. Please try again."
        ),
        "scroll_focus_changed": "The active window changed, so I stopped scrolling.",
        "scroll_control_setup_required": (
            "Set up desktop scroll access in Desktop Actions first."
        ),
        "scroll_unavailable": "I couldn't scroll. Please check the screen.",
        "visible_control_uncertain": (
            "I couldn't find one clear visible option with that name."
        ),
        "visible_control_capture_geometry_required": (
            "The capture extension is missing coordinate information. After "
            "installing the update, save your work, log out of Ubuntu and log back in."
        ),
        "visible_control_screen_access_required": (
            "Enable Screen Access in KYRIN to find visible options."
        ),
        "visible_control_focus_changed": "The focused window changed, so I stopped.",
        "visible_control_target_changed": (
            "The option or window moved. Please try again."
        ),
        "visible_control_setup_required": (
            "Desktop click permission is enabled, but its system grant is not "
            "saved. In Desktop Actions, save settings, press 'Set up desktop "
            "click access now', and approve Remote Desktop once."
        ),
        "visible_control_state_unavailable": (
            "The control did not expose its state, so I left it unchanged."
        ),
        "visible_control_sensitive": (
            "This effect needs a dedicated tool and permission; "
            "generic control cannot run it."
        ),
        "visible_control_capability_required": (
            "The tool does not support this control operation."
        ),
        "visible_control_confirmation_declined": (
            "This operation was not approved and was not run."
        ),
        "window_close_confirmation_required": (
            "Closing needs confirmation for this window; "
            "confirmation UI is unavailable."
        ),
        "window_close_confirmation_declined": "Window close was not approved or run.",
        "visible_control_confirmation_expired": (
            "The consent or target window expired; issue a new command."
        ),
        "visible_control_risk_unknown": (
            "This option's effect is unknown and it cannot run without confirmation."
        ),
        "visible_control_unavailable": (
            "Desktop control was unavailable. Please check the screen."
        ),
        "scroll_dispatched": (
            "I sent the scroll input, but haven't verified that the page moved."
        ),
        "chat_unverified": (
            "I couldn't verify that the chat opened. Please check the screen."
        ),
        "telegram_menu_uncertain": (
            "I couldn't confidently find that Telegram menu item."
        ),
        "telegram_setting_not_found": (
            "I couldn't confidently find that item in Telegram Settings."
        ),
        "telegram_settings_not_open": ("Telegram Settings is not open. Open it first."),
        "telegram_settings_navigation_uncertain": (
            "I couldn't verify the return to Telegram Settings, so I stopped."
        ),
        "telegram_setting_requires_value": (
            "That item is a settings control, not a page to open. No change was made."
        ),
        "telegram_input_unknown": (
            "The Telegram input result is unclear. Please check the screen."
        ),
        "telegram_view_dispatched": (
            "I sent the command to Telegram, but haven't verified the destination."
        ),
        "telegram_search_dispatched": (
            "I sent the search input to Telegram, but haven't verified the field."
        ),
        "no_window": "I couldn't find an open window for that app.",
        "unavailable": "This window does not support the requested change.",
        "multiple_windows": (
            "That app has multiple windows. Focus the one you want, then try again."
        ),
        "window_unverified": (
            "I couldn't verify the window change. Please check the screen."
        ),
        "window_state_changed": (
            "The window list changed. Please show the Terminal windows again."
        ),
        "dependency_unverified": (
            "A prerequisite was not verified, so I skipped the dependent step."
        ),
        "confirmed": "Done.",
        "confirmed_active_app": "The requested app is now active.",
        "launch_accepted": (
            "The request was accepted; completion has not been confirmed."
        ),
        "dispatched_unverified": (
            "I sent the input, but completion has not been confirmed."
        ),
        "chat_selection_dispatched": (
            "I clicked the selected result, but identical titles prevent "
            "exact chat identity confirmation."
        ),
        "unknown": "The result is unclear. Please check what happened.",
        "failed": "I couldn't complete that action. Please try again.",
        "processing_delayed": "I'm processing earlier speech. Please pause briefly.",
        "processing_ready": "You can continue now.",
        "processing_overloaded": (
            "Audio processing fell behind and some speech may have been lost. "
            "Please pause and repeat it."
        ),
        "audio_input_failure": "Audio input stopped. Please check your microphone.",
        "compute_unavailable": (
            "The selected processor for speech recognition is unavailable. "
            "Please check the processing settings."
        ),
        "model_unavailable": (
            "The speech recognition model was not found. "
            "Please check its installation or path."
        ),
        "transcription_failure": (
            "Speech recognition encountered a problem. Please try again."
        ),
        "general_failure": "Something went wrong. Please try again.",
        "listening_retry": "I'm trying to restart speech input.",
    },
}

_APP_NAMES: dict[str, dict[str, str]] = {
    "fa": {"telegram": "تلگرام", "whatsapp": "واتساپ", "browser": "مرورگر"},
    "en": {"telegram": "Telegram", "whatsapp": "WhatsApp", "browser": "browser"},
}


@dataclass(frozen=True, slots=True)
class PresentedResponse:
    """Ready-to-display text and a requested output channel, not synthesized audio."""

    stream_id: int | None
    segment_id: int | None
    text: str
    channel: ResponseChannel
    language: str


class ResponsePresenter:
    """Localize each event; use the session language when its locale is absent."""

    def __init__(self, language: str) -> None:
        self.language = _supported_language(language) or "en"

    def present(
        self, event: ResponseRequest | ActionNotice | ActionFeedback | SystemNotice
    ) -> PresentedResponse:
        language = _supported_language(event.language) or self.language
        messages = _TEXT[language]
        if isinstance(event, ResponseRequest):
            text = (
                event.message
                if event.kind is ResponseKind.CONVERSATION
                else self._command_text(event, messages, language)
            )
            assert text is not None
            stream_id, segment_id = event.stream_id, event.segment_id
        elif isinstance(event, ActionNotice):
            text = (
                messages["unsupported_chat"]
                if event.reason.value == "unsupported"
                and event.intent.kind is CommandKind.OPEN_CHAT
                else messages[event.reason.value]
            )
            stream_id, segment_id = event.key.stream_id, event.key.segment_id
        elif isinstance(event, SystemNotice):
            text = messages[event.kind.value]
            stream_id, segment_id = None, None
        else:
            # error_code is diagnostic data; never expose it as user text.
            if (
                event.outcome is ActionOutcome.CONFIRMED
                and event.intent.kind is CommandKind.OPEN_APP
                and event.observed_active_app == event.intent.target
            ):
                text = messages["confirmed_active_app"]
            elif (
                event.outcome is ActionOutcome.LAUNCH_ACCEPTED
                and event.intent.kind
                in (CommandKind.SCROLL_UP, CommandKind.SCROLL_DOWN)
            ):
                text = messages["scroll_dispatched"]
            elif (
                event.outcome
                in (ActionOutcome.LAUNCH_ACCEPTED, ActionOutcome.DISPATCHED_UNVERIFIED)
                and event.intent.kind is CommandKind.OPEN_CHAT
            ):
                text = messages[
                    "chat_selection_dispatched"
                    if event.outcome is ActionOutcome.LAUNCH_ACCEPTED
                    else "dispatched_unverified"
                ]
            elif event.outcome in (
                ActionOutcome.LAUNCH_ACCEPTED,
                ActionOutcome.DISPATCHED_UNVERIFIED,
            ) and event.intent.kind in (
                CommandKind.TELEGRAM_VIEW,
                CommandKind.TELEGRAM_SETTINGS,
            ):
                text = messages["telegram_view_dispatched"]
            elif event.outcome in (
                ActionOutcome.LAUNCH_ACCEPTED,
                ActionOutcome.DISPATCHED_UNVERIFIED,
            ) and event.intent.kind in (
                CommandKind.TELEGRAM_SEARCH_FOCUS,
                CommandKind.TELEGRAM_SEARCH,
            ):
                text = messages["telegram_search_dispatched"]
            elif (
                event.error_code in {"unsupported_action", "unsupported_chat"}
                and event.intent.kind is CommandKind.OPEN_CHAT
            ):
                text = messages[
                    "unsupported_chat"
                    if event.error_code == "unsupported_action"
                    else "unsupported_chat_target"
                ]
            elif event.error_code in {
                "screen_access_required",
                "telegram_not_active",
                "telegram_focus_changed",
                "chat_target_changed",
                "chat_unverified",
                "telegram_menu_uncertain",
                "telegram_setting_not_found",
                "telegram_setting_requires_value",
                "telegram_settings_not_open",
                "telegram_settings_navigation_uncertain",
                "telegram_input_unknown",
                "chat_search_uncertain",
                "visible_chat_uncertain",
                "chat_selection_expired",
                "chat_selection_cancelled",
                "telegram_control_setup_required",
                "telegram_control_unavailable",
                "scroll_focus_changed",
                "scroll_control_setup_required",
                "scroll_unavailable",
                "visible_control_uncertain",
                "visible_control_capture_geometry_required",
                "visible_control_screen_access_required",
                "visible_control_focus_changed",
                "visible_control_target_changed",
                "visible_control_setup_required",
                "visible_control_state_unavailable",
                "visible_control_sensitive",
                "visible_control_risk_unknown",
                "visible_control_capability_required",
                "visible_control_confirmation_declined",
                "window_close_confirmation_required",
                "window_close_confirmation_declined",
                "visible_control_confirmation_expired",
                "visible_control_unavailable",
                "no_window",
                "multiple_windows",
                "unavailable",
                "window_unverified",
                "window_state_changed",
            }:
                text = (
                    messages[event.error_code].format(target=event.intent.target)
                    if event.error_code
                    in {"chat_search_uncertain", "visible_chat_uncertain"}
                    else messages[event.error_code]
                )
            elif event.error_code is not None and event.error_code.startswith(
                (
                    "chat_search_uncertain:",
                    "visible_chat_uncertain:",
                    "visible_control_target_changed:",
                )
            ):
                code = event.error_code.split(":", 1)[0]
                text = (
                    messages[code].format(target=event.intent.target)
                    if code in {"chat_search_uncertain", "visible_chat_uncertain"}
                    else messages[code]
                )
            else:
                text = messages[event.outcome.value]
            stream_id, segment_id = event.key.stream_id, event.key.segment_id
        response_language = (
            event.language
            if isinstance(event, ResponseRequest)
            and event.kind is ResponseKind.CONVERSATION
            and event.language is not None
            else language
        )
        return PresentedResponse(
            stream_id, segment_id, text, event.channel, response_language
        )

    def _command_text(
        self, event: ResponseRequest, messages: dict[str, str], language: str
    ) -> str:
        if event.kind is ResponseKind.REPEAT_COMMAND:
            return messages[event.kind.value]
        if event.kind in (ResponseKind.CONFIRM_APP, ResponseKind.CHOOSE_APP_OR_CHAT):
            target = _APP_NAMES[language].get(event.target or "", event.target)
            return messages[event.kind.value].format(target=target)
        if event.kind is ResponseKind.CHOOSE_APP:
            if len(set(event.app_candidates)) == 1:
                return messages["choose_app_duplicate"].format(
                    target=event.app_candidates[0]
                )
            template = (
                "choose_app_to_close"
                if event.operation_candidates == (CommandKind.CLOSE_APP_WINDOW,)
                else event.kind.value
            )
            return messages[template].format(
                options=("؛ " if language == "fa" else "; ").join(
                    f"{index}. {name}"
                    for index, name in enumerate(event.app_candidates, start=1)
                )
                + "."
            )
        if event.kind is ResponseKind.CHOOSE_OPERATION:
            labels = {
                "en": {
                    CommandKind.OPEN_APP: "Open or bring forward",
                    CommandKind.MINIMIZE_APP: "Minimize",
                    CommandKind.CLOSE_APP_WINDOW: "Close",
                    CommandKind.UNMAXIMIZE_APP: "Restore normal size",
                    CommandKind.NEW_APP_WINDOW: "New window",
                    CommandKind.NEW_APP_TAB: "New tab",
                    CommandKind.APP_PREFERENCES: "Preferences",
                    CommandKind.SHOW_ALL_WINDOWS: "Show all open windows",
                    CommandKind.SHOW_APP_WINDOWS: "Choose a Terminal window",
                },
                "fa": {
                    CommandKind.OPEN_APP: "بازکردن یا جلوآوردن",
                    CommandKind.MINIMIZE_APP: "کوچک‌کردن",
                    CommandKind.CLOSE_APP_WINDOW: "بستن",
                    CommandKind.UNMAXIMIZE_APP: "برگرداندن اندازهٔ عادی",
                    CommandKind.NEW_APP_WINDOW: "پنجرهٔ تازه",
                    CommandKind.NEW_APP_TAB: "تب تازه",
                    CommandKind.APP_PREFERENCES: "تنظیمات",
                    CommandKind.SHOW_ALL_WINDOWS: "نمایش همهٔ پنجره‌های باز",
                    CommandKind.SHOW_APP_WINDOWS: "انتخاب پنجرهٔ ترمینال",
                },
            }[language]
            options = ("؛ " if language == "fa" else "; ").join(
                f"{index}. {labels[kind]}"
                for index, kind in enumerate(event.operation_candidates, start=1)
            )
            if event.operation_candidates == (CommandKind.OPEN_APP,):
                template = messages["choose_operation_only_open"]
            elif CommandKind.OPEN_APP in event.operation_candidates:
                template = messages["choose_operation_open"]
            else:
                template = messages["choose_operation"]
            return template.format(target=event.target, options=options)
        if event.kind is ResponseKind.CONFIRM_ACTION:
            operation = event.operation_candidates[0]
            app_actions = {
                "en": {
                    CommandKind.RESTORE_APP: "bring {target} forward",
                    CommandKind.MINIMIZE_APP: "minimize {target}",
                    CommandKind.MAXIMIZE_APP: "maximize {target}",
                    CommandKind.UNMAXIMIZE_APP: "restore {target} to normal size",
                    CommandKind.FULLSCREEN_APP: "make {target} full screen",
                    CommandKind.UNFULLSCREEN_APP: "leave full screen in {target}",
                },
                "fa": {
                    CommandKind.RESTORE_APP: "{target} را جلو بیاورم",
                    CommandKind.MINIMIZE_APP: "{target} را کوچک کنم",
                    CommandKind.MAXIMIZE_APP: "{target} را بزرگ کنم",
                    CommandKind.UNMAXIMIZE_APP: "اندازهٔ {target} را عادی کنم",
                    CommandKind.FULLSCREEN_APP: "{target} را تمام‌صفحه کنم",
                    CommandKind.UNFULLSCREEN_APP: (
                        "{target} را از حالت تمام‌صفحه خارج کنم"
                    ),
                },
            }
            if operation in app_actions[language]:
                action = app_actions[language][operation].format(target=event.target)
                return (
                    f"آیا می‌خواهید {action}؟ بله یا خیر؟"
                    if language == "fa"
                    else f"Do you want me to {action}? Yes or no?"
                )
            return messages["confirm_action"].format(target=event.target)
        if event.kind is ResponseKind.CONFIRM_NUMBERED_CLOSE:
            return messages["confirm_numbered_close"].format(number=event.window_index)
        if event.kind is ResponseKind.CHOOSE_WINDOW:
            if event.target == "open applications":
                return messages["choose_open_window"]
            return messages["choose_window"].format(target=event.target)
        if len(event.app_candidates) != 2:
            return messages[event.kind.value]
        first, second = event.app_candidates
        names = _APP_NAMES[language]
        return messages["choose_chat_app_pair"].format(
            target=event.target,
            first=names.get(first, first),
            second=names.get(second, second),
        )


def _supported_language(language: str | None) -> str | None:
    if language is None:
        return None
    primary = language.strip().replace("_", "-").split("-", maxsplit=1)[0].casefold()
    return primary if primary in _TEXT else None
