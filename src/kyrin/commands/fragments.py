"""Join only a short, explicit operation fragment to its nearby target."""

import re
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass
from time import monotonic

_PREFIX_OPERATIONS = frozenset(
    {
        "open", "go to", "launch", "start", "switch to",
        "restore", "show", "bring back", "minimize", "hide",
        "close", "exit", "quit", "maximize", "unmaximize",
        "fullscreen", "exit fullscreen on",
    }
)
_SUFFIX_OPERATIONS = frozenset(
    {
        "باز کن", "ببند", "کوچک کن", "پنهان کن",
        "نشان بده", "دوباره نشان بده", "برگردان", "بزرگ کن",
        "تمام صفحه کن", "به اندازه عادی برگردان",
        "از تمام صفحه خارج کن",
    }
)
_ANSWER_OR_CANCEL = frozenset(
    {
        "yes", "no", "ja", "nein", "oui", "non", "sí", "si", "да",
        "بله", "آره", "نه", "خیر", "لغو", "cancel", "是", "不是",
    }
)
_NEW_COMMAND = re.compile(
    r"^(?:please\s+)?(?:"
    + "|".join(
        re.escape(word)
        for word in sorted(_PREFIX_OPERATIONS, key=len, reverse=True)
    )
    + r"|do not|don't)\b",
    re.IGNORECASE,
)
_UNSAFE_CONTINUATION = re.compile(
    r"\b(?:and|then|not|never|cancel|don't|dont)\b|\bdo not\b"
)
_PERSIAN_COMMAND = re.compile(
    "|".join(
        re.escape(word)
        for word in sorted(_SUFFIX_OPERATIONS | {"باز نکن"}, key=len, reverse=True)
    )
)


def _normalize(text: str) -> str:
    value = unicodedata.normalize("NFKC", text).casefold()
    value = value.replace("ي", "ی").replace("ك", "ک").replace("‌", " ")
    return " ".join(value.strip().rstrip(".!?؟。").split())


@dataclass(frozen=True, slots=True)
class _Fragment:
    operation: str
    target_first: bool
    recorded_at: float


class CommandFragmentBuffer:
    """Ephemeral command assembly; old dialogue is never executable input."""

    def __init__(
        self, *, window_seconds: float = 4.0, clock: Callable[[], float] = monotonic
    ) -> None:
        if window_seconds <= 0:
            raise ValueError("window_seconds must be positive")
        self._window_seconds = window_seconds
        self._clock = clock
        self._fragment: _Fragment | None = None

    def hold(self, text: str) -> bool:
        operation = _normalize(text)
        if operation not in _PREFIX_OPERATIONS | _SUFFIX_OPERATIONS:
            return False
        self._fragment = _Fragment(
            operation, operation in _SUFFIX_OPERATIONS, self._clock()
        )
        return True

    def combine(self, text: str) -> str | None:
        fragment = self._fragment
        self._fragment = None
        if (
            fragment is None
            or self._clock() - fragment.recorded_at > self._window_seconds
        ):
            return None
        target = text.strip()
        if (
            not target
            or len(target) > 80
            or _normalize(target) in _ANSWER_OR_CANCEL
            or _NEW_COMMAND.match(target)
            or _UNSAFE_CONTINUATION.search(_normalize(target))
            or _PERSIAN_COMMAND.search(_normalize(target))
        ):
            return None
        return (
            f"{target} را {fragment.operation}"
            if fragment.target_first
            else f"{fragment.operation} {target}"
        )

    def clear(self) -> None:
        self._fragment = None
