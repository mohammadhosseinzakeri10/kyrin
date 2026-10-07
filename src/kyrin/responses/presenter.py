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
        "repeat_command": "متوجه نشدم. لطفاً فرمان را دوباره بگویید.",
        "choose_chat_app": "چت را در کدام برنامه باز کنم؟",
        "choose_chat_app_pair": "چت {target} را در {first} باز کنم یا {second}؟",
        "confirm_app": "منظورتان برنامهٔ {target} است؟",
        "choose_app_or_chat": (
            "منظورتان برنامهٔ {target} است یا یک چت؟ لطفاً بگویید «برنامه» یا «چت»."
        ),
        "choose_app": "منظورتان کدام برنامه است: {options}؟",
        "choose_app_duplicate": (
            "چند برنامه با نام {target} پیدا شد. لطفاً نام متفاوتی بگویید."
        ),
        "not_allowed": "اجازهٔ انجام این کار را ندارم.",
        "confirmation_required": "برای انجام این کار به تأیید شما نیاز دارم.",
        "busy": "فعلاً مشغولم. لطفاً کمی بعد دوباره تلاش کنید.",
        "cancelled": "انجام این کار لغو شد.",
        "unsupported": "این بخش از فرمان هنوز پشتیبانی نمی‌شود.",
        "unsupported_chat": "هنوز نمی‌توانم چت را باز کنم.",
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
        "repeat_command": "I didn't understand. Please repeat the command.",
        "choose_chat_app": "Which app should I open the chat in?",
        "choose_chat_app_pair": (
            "Should I open {target}'s chat in {first} or {second}?"
        ),
        "confirm_app": "Did you mean the {target} app?",
        "choose_app_or_chat": (
            "Do you mean the {target} app or a chat? Please say app or chat."
        ),
        "choose_app": "Which app did you mean: {options}?",
        "choose_app_duplicate": (
            "Multiple apps are named {target}. Please use a different name."
        ),
        "not_allowed": "I can't perform that action.",
        "confirmation_required": "Please confirm before I do that.",
        "busy": "I'm still processing. Please wait and try again.",
        "cancelled": "That action was cancelled.",
        "unsupported": "I can't perform this step yet.",
        "unsupported_chat": "I can't open chats yet.",
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
    "fa": {"telegram": "تلگرام", "whatsapp": "واتساپ"},
    "en": {"telegram": "Telegram", "whatsapp": "WhatsApp"},
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
            text = self._command_text(event, messages, language)
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
                event.error_code == "unsupported_action"
                and event.intent.kind is CommandKind.OPEN_CHAT
            ):
                text = messages["unsupported_chat"]
            else:
                text = messages[event.outcome.value]
            stream_id, segment_id = event.key.stream_id, event.key.segment_id
        return PresentedResponse(stream_id, segment_id, text, event.channel, language)

    def _command_text(
        self, event: ResponseRequest, messages: dict[str, str], language: str
    ) -> str:
        if event.kind is ResponseKind.REPEAT_COMMAND:
            return messages[event.kind.value]
        if event.kind in (ResponseKind.CONFIRM_APP, ResponseKind.CHOOSE_APP_OR_CHAT):
            return messages[event.kind.value].format(target=event.target)
        if event.kind is ResponseKind.CHOOSE_APP:
            if len(set(event.app_candidates)) == 1:
                return messages["choose_app_duplicate"].format(
                    target=event.app_candidates[0]
                )
            return messages[event.kind.value].format(
                options="، ".join(event.app_candidates)
                if language == "fa"
                else ", ".join(event.app_candidates)
            )
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
