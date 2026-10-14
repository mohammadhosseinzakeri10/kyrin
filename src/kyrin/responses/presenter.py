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
            "منظورتان برنامهٔ {target} است یا یک چت؟ لطفاً بگویید «برنامه» یا «چت»."
        ),
        "choose_app": "کدام برنامه را می‌خواهید؟ {options} شماره یا نام را بگویید.",
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
            "یک نتیجهٔ یکتا و دقیق برای این چت پیدا نکردم؛ لطفاً نام کامل‌تر را بگویید."
        ),
        "screen_access_required": "برای بررسی چت، دسترسی صفحه را در برنامه فعال کنید.",
        "telegram_not_active": (
            "تلگرام فعال نیست؛ لطفاً آن را جلو بیاورید و دوباره بگویید."
        ),
        "telegram_focus_changed": "پنجرهٔ فعال تغییر کرد؛ فرمان چت متوقف شد.",
        "chat_unverified": "بازشدن چت را نتوانستم تأیید کنم. لطفاً صفحه را بررسی کنید.",
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
            "فعال‌بودن برنامهٔ موردنظر تأیید نشد؛ برای جلوگیری از رفتن به چت "
            "نادرست، ادامه ندادم."
        ),
        "confirmed": "انجام شد.",
        "confirmed_active_app": "برنامهٔ موردنظر اکنون فعال است.",
        "launch_accepted": (
            "درخواست انجام کار پذیرفته شد؛ نتیجهٔ آن هنوز تأیید نشده است."
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
            "Do you mean the {target} app or a chat? Please say app or chat."
        ),
        "choose_app": "Which app do you mean? {options} Say its number or name.",
        "choose_operation": (
            "What should I do with {target}? {options} Say a number or no."
        ),
        "choose_operation_open": (
            "What should I do with {target}? {options} Say yes to open or "
            "bring it forward, no to cancel, or choose an option number."
        ),
        "choose_operation_only_open": "Open {target}? Say yes or no.",
        "choose_window": (
            "Only {target} windows are shown. "
            "Say a window number or click its preview."
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
            "I couldn't find one exact chat result. Please say a more specific name."
        ),
        "screen_access_required": "Enable Screen Access in KYRIN to verify the chat.",
        "telegram_not_active": (
            "Telegram is not active. Bring it forward and try again."
        ),
        "telegram_focus_changed": (
            "The active window changed, so I stopped the chat command."
        ),
        "chat_unverified": (
            "I couldn't verify that the chat opened. Please check the screen."
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
            "I couldn't verify that the intended app is active, so I stopped "
            "before opening the chat."
        ),
        "confirmed": "Done.",
        "confirmed_active_app": "The requested app is now active.",
        "launch_accepted": (
            "The request was accepted; completion has not been confirmed."
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
                "chat_unverified",
                "chat_search_uncertain",
                "no_window",
                "multiple_windows",
                "unavailable",
                "window_unverified",
                "window_state_changed",
            }:
                text = messages[event.error_code]
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
            return messages[event.kind.value].format(
                options=("؛ " if language == "fa" else "; ").join(
                    f"{index}. {name}"
                    for index, name in enumerate(event.app_candidates, start=1)
                ) + "."
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
            return template.format(
                target=event.target, options=options
            )
        if event.kind is ResponseKind.CONFIRM_ACTION:
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
