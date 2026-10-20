"""Spoken selection when several matching Telegram chat rows are visible."""

import logging
from collections.abc import Callable
from dataclasses import dataclass
from threading import Event, Lock, Thread, Timer
from time import monotonic

from kyrin.actions.models import (
    ActionFeedback,
    ActionOutcome,
    ActionRequest,
    ActionResult,
)
from kyrin.actions.telegram_verification import ChatSearchChoices
from kyrin.commands.models import ResponseChannel, ResponseKind, ResponseRequest
from kyrin.text_normalization import fold_case

_TIMEOUT_SECONDS = 45.0
_LOGGER = logging.getLogger(__name__)
_NUMBERS = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "یک": 1,
    "دو": 2,
    "سه": 3,
    "چهار": 4,
    "پنج": 5,
    "شش": 6,
    "هفت": 7,
    "هشت": 8,
    "نه": 9,
    "ده": 10,
}
_ORDINALS = {
    "first": 1,
    "second": 2,
    "third": 3,
    "fourth": 4,
    "fifth": 5,
    "sixth": 6,
    "seventh": 7,
    "eighth": 8,
    "ninth": 9,
    "tenth": 10,
    "اول": 1,
    "دوم": 2,
    "سوم": 3,
    "چهارم": 4,
    "پنجم": 5,
    "ششم": 6,
    "هفتم": 7,
    "هشتم": 8,
    "نهم": 9,
    "دهم": 10,
}
_ORDINAL_DIGITS = {
    f"{number}{suffix}": number
    for number, suffix in (
        (1, "st"),
        (2, "nd"),
        (3, "rd"),
        *((number, "th") for number in range(4, 11)),
    )
}
# Observed STT spellings of "number two". Apply them only while a Telegram
# chat-choice prompt is pending; other numbered menus keep their strict parser.
_OBSERVED_CHAT_CHOICE_ALIASES = {
    "non-bear too": 2,
    "nombertoo": 2,
}
_CHOICE_PREFIXES = {
    "number",
    "nomber",
    "option",
    "choice",
    "result",
    "chat",
    "شماره",
    "شمارهٔ",
    "گزینه",
    "گزینهٔ",
    "نتیجه",
    "چت",
}
_CHOICE_SUFFIXES = {
    "one",
    "option",
    "choice",
    "result",
    "chat",
    "گزینه",
    "نتیجه",
    "چت",
}


@dataclass(frozen=True, slots=True)
class _Pending:
    request: ActionRequest
    identity: tuple[str, int]
    target: str
    choices: ChatSearchChoices
    expires_at: float
    page: int = 1


@dataclass(slots=True)
class _Active:
    cancellation: Event
    report_after_spoken_cancel: bool = False


Completion = Callable[
    [ActionRequest, tuple[str, int], str, ChatSearchChoices, int | None, Event],
    ActionResult,
]
PageNavigation = Callable[
    [tuple[str, int], str, ChatSearchChoices, Event],
    ChatSearchChoices | None,
]


class TelegramChatSelection:
    """Keep one bounded choice; a spoken answer alone never grants a click."""

    def __init__(
        self,
        on_prompt: Callable[[ResponseRequest], None],
        on_feedback: Callable[[ActionFeedback], None],
    ) -> None:
        self._on_prompt = on_prompt
        self._on_feedback = on_feedback
        self._completion: Completion | None = None
        self._page_navigation: PageNavigation | None = None
        self._pending: _Pending | None = None
        self._timer: Timer | None = None
        self._active: dict[Event, _Active] = {}
        self._lock = Lock()

    def set_completion(self, completion: Completion) -> None:
        self._completion = completion

    def set_page_navigation(self, navigation: PageNavigation) -> None:
        self._page_navigation = navigation

    def begin(
        self,
        request: ActionRequest,
        identity: tuple[str, int],
        target: str,
        choices: ChatSearchChoices,
    ) -> bool:
        # Without a visible global-section boundary, another local chat may
        # be below the viewport. Keep the choice open for bounded paging.
        local_choice = bool(choices.local_results) and (
            len(choices.local_results) >= 2 or not choices.global_section_verified
        )
        global_choice = (
            not choices.local_results
            and choices.global_section_verified
            and bool(choices.global_results)
        )
        if not (local_choice or global_choice) or self._completion is None:
            return False
        pending = _Pending(
            request,
            identity,
            target,
            choices,
            monotonic() + _TIMEOUT_SECONDS,
        )
        with self._lock:
            if self._timer is not None:
                self._timer.cancel()
            for active in self._active.values():
                active.cancellation.set()
                active.report_after_spoken_cancel = False
            self._pending = pending
            timer = Timer(_TIMEOUT_SECONDS, lambda: self._expire(pending))
            timer.daemon = True
            self._timer = timer
            timer.start()
        self._prompt(pending)
        return True

    def on_final_speech(self, speech: str) -> bool:
        answer = fold_case(speech).strip(" .!?؟")
        with self._lock:
            pending = self._pending
            if pending is None:
                if answer in {"cancel", "no", "لغو", "خیر", "نه"} and self._active:
                    for active in self._active.values():
                        active.cancellation.set()
                        active.report_after_spoken_cancel = True
                    return True
                return False
            if monotonic() >= pending.expires_at:
                self._pending = None
                self._cancel_timer_locked()
                expired = True
            else:
                expired = False
        if expired:
            self._feedback(pending.request, "chat_selection_expired")
            return True

        if answer in {"cancel", "no", "لغو", "خیر", "نه"}:
            with self._lock:
                cancelled = self._pending == pending
                if cancelled:
                    self._pending = None
                    self._cancel_timer_locked()
            if cancelled:
                self._feedback(pending.request, "chat_selection_cancelled")
            return True

        if answer in {
            "next",
            "next page",
            "more",
            "more results",
            "بعدی",
            "نتایج بعدی",
        }:
            if (
                pending.choices.source == "visible"
                or self._page_navigation is None
                or pending.page >= 5
            ):
                self._prompt(pending)
            else:
                self._navigate(pending)
            return True

        number = self._number(answer)
        if number is not None and 1 <= number <= len(
            pending.choices.selectable_results
        ):
            self._complete(pending, number)
            return True
        self._prompt(pending)
        return True

    def cancel(self) -> None:
        with self._lock:
            pending = self._pending
            self._pending = None
            self._cancel_timer_locked()
            for active in self._active.values():
                active.cancellation.set()
                active.report_after_spoken_cancel = False
        if pending is not None:
            self._feedback(pending.request, "chat_selection_cancelled")

    def _cancel_timer_locked(self) -> None:
        if self._timer is not None:
            self._timer.cancel()
            self._timer = None

    def _expire(self, pending: _Pending) -> None:
        with self._lock:
            if self._pending != pending:
                return
            self._pending = None
            self._timer = None
        self._feedback(pending.request, "chat_selection_expired")

    def _feedback(self, request: ActionRequest, error_code: str) -> None:
        self._on_feedback(
            ActionFeedback(
                request.key,
                request.intent,
                ActionOutcome.FAILED,
                ResponseChannel.TEXT_AND_VOICE,
                error_code,
                request.language,
            )
        )

    @staticmethod
    def _number(answer: str) -> int | None:
        if answer in _OBSERVED_CHAT_CHOICE_ALIASES:
            return _OBSERVED_CHAT_CHOICE_ALIASES[answer]
        words = answer.split()
        if words and words[0] in {"choose", "select", "pick"}:
            words = words[1:]
        if words and words[0] == "the":
            words = words[1:]
        if len(words) > 1 and words[0] in _CHOICE_PREFIXES:
            words = words[1:]
        if len(words) > 1 and words[0] == "number":
            words = words[1:]
        if (
            len(words) == 2
            and (words[0] in _ORDINALS or words[0] in _ORDINAL_DIGITS)
            and words[1] in _CHOICE_SUFFIXES
        ):
            words = words[:1]
        if len(words) != 1:
            return None
        token = words[0]
        if token.isdecimal():
            return int(token)
        return _NUMBERS.get(token) or _ORDINALS.get(token) or _ORDINAL_DIGITS.get(token)

    def _complete(self, pending: _Pending, number: int | None) -> None:
        with self._lock:
            if self._pending != pending:
                return
            self._pending = None
            self._cancel_timer_locked()
            cancellation = Event()
            self._active[cancellation] = _Active(cancellation)
        completion = self._completion
        assert completion is not None

        def work() -> None:
            try:
                result = completion(
                    pending.request,
                    pending.identity,
                    pending.target,
                    pending.choices,
                    number,
                    cancellation,
                )
            except Exception:
                # The OS action may have occurred before an adapter raised.
                _LOGGER.exception(
                    "Telegram selection failed for %s", pending.request.key
                )
                result = ActionResult(
                    pending.request.key,
                    ActionOutcome.UNKNOWN,
                    error_code="executor_exception",
                )
            with self._lock:
                active = self._active.pop(cancellation)
                report = (
                    not cancellation.is_set()
                    or active.report_after_spoken_cancel
                )
            if report:
                self._on_feedback(
                    ActionFeedback(
                        result.key,
                        pending.request.intent,
                        result.outcome,
                        ResponseChannel.TEXT_ONLY
                        if result.error_code is None
                        else ResponseChannel.TEXT_AND_VOICE,
                        result.error_code,
                        pending.request.language,
                        result.observed_active_app,
                    )
                )

        Thread(target=work, name="kyrin-telegram-selection", daemon=True).start()

    def _navigate(self, pending: _Pending) -> None:
        with self._lock:
            if self._pending != pending:
                return
            self._pending = None
            self._cancel_timer_locked()
            cancellation = Event()
            self._active[cancellation] = _Active(cancellation)
        navigation = self._page_navigation
        assert navigation is not None

        def work() -> None:
            try:
                choices = navigation(
                    pending.identity, pending.target, pending.choices, cancellation
                )
            except Exception:
                _LOGGER.exception("Telegram result paging failed")
                choices = None
            with self._lock:
                active = self._active.pop(cancellation)
                was_cancelled = cancellation.is_set()
                if was_cancelled:
                    report_cancel = active.report_after_spoken_cancel
                    next_pending = None
                elif choices is None:
                    report_cancel = False
                    next_pending = None
                else:
                    report_cancel = False
                    next_pending = _Pending(
                        pending.request,
                        pending.identity,
                        pending.target,
                        choices,
                        monotonic() + _TIMEOUT_SECONDS,
                        pending.page + 1,
                    )
                    self._pending = next_pending
                    timer = Timer(
                        _TIMEOUT_SECONDS,
                        lambda: self._expire(next_pending),
                    )
                    timer.daemon = True
                    self._timer = timer
                    timer.start()
            if was_cancelled:
                if report_cancel:
                    self._feedback(pending.request, "chat_selection_cancelled")
                return
            if next_pending is None:
                self._feedback(pending.request, "chat_search_uncertain")
            else:
                self._prompt(next_pending)

        Thread(target=work, name="kyrin-telegram-paging", daemon=True).start()

    def _prompt(self, pending: _Pending) -> None:
        count = len(pending.choices.selectable_results)
        if pending.choices.source == "visible":
            english = f"I found {count} visible chats with that name. "
            persian = f"{count} چت قابل‌دیدن با این نام پیدا شد. "
        elif pending.choices.local_results:
            place = " on this page" if pending.page > 1 else ""
            english = f"I found {count} personal chats with that name{place}. "
            persian = f"{count} چت شخصی با این نام در این صفحه پیدا شد. "
        else:
            place = " on this page" if pending.page > 1 else ""
            english = (
                f"I found {count} matching global search results{place} "
                "in Telegram. "
            )
            persian = f"{count} نتیجهٔ سراسری با این نام در این صفحه پیدا شد. "
        if count == 1:
            english += "Say one or the first to open it."
            persian += "برای بازکردن آن «یک» یا «اول» را بگویید."
        else:
            english += (
                f"Choose 1 to {count}, top to bottom. "
                "For example, say number two, two, or the second."
            )
            persian += (
                f"از بالا شمارهٔ ۱ تا {count} را انتخاب کنید؛ "
                "مثلاً «شمارهٔ دو»، «دو» یا «دوم» را بگویید."
            )
        if (
            pending.choices.source == "search"
            and self._page_navigation is not None
            and pending.page < 5
        ):
            english += " Say next for more visible results."
            persian += " برای دیدن نتیجه‌های بعدی «بعدی» را بگویید."
        self._say(pending.request, english, persian)

    def _say(self, request: ActionRequest, english: str, persian: str) -> None:
        is_persian = (request.language or "").startswith("fa")
        self._on_prompt(
            ResponseRequest(
                request.key.segment_id,
                ResponseKind.CONVERSATION,
                ResponseChannel.TEXT_AND_VOICE,
                stream_id=request.key.stream_id,
                language=request.language or "en",
                message=persian if is_persian else english,
            )
        )
