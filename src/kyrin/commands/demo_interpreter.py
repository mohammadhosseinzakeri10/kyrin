"""Tiny offline demonstration interpreter; not the multilingual product engine."""

import re
import unicodedata

from kyrin.commands.context_resolver import (
    AppClarification,
    ContextResolver,
)
from kyrin.commands.interpreter import (
    IncompleteCommand,
    Interpretation,
    NeedsClarification,
    NotACommand,
    ReadyCommand,
    UnrecognizedCommand,
)
from kyrin.commands.models import (
    CommandContext,
    CommandIntent,
    CommandKind,
    PendingClarification,
)

_APPS = {
    "تلگرام": "telegram",
    "telegram": "telegram",
    "مرورگر": "browser",
    "browser": "browser",
    "واتساپ": "whatsapp",
    "whatsapp": "whatsapp",
}
_CHAT_APPS = frozenset({"telegram", "whatsapp"})
_OPEN_APP_FA = re.compile(r"^(تلگرام|مرورگر) را باز کن$")
_OPEN_APP_EN = re.compile(r"^(?:open|go to) (?:the )?(telegram|browser)$")
_OPEN_CHAT_WITH_APP_FA = re.compile(r"^چت (.+?) را در (تلگرام|واتساپ) باز کن$")
_OPEN_CHAT_FA = re.compile(r"^(?:چت|گفتگوی) (.+?) را باز کن$")
_GO_CHAT_FA = re.compile(r"^به (?:چت|گفتگوی) (.+?) برو$")
_OPEN_CHAT_EN = re.compile(r"^(?:open|go to) chat (.+)$")
_WAKE_PREFIXES = ("کایرین ", "کایری ", "kyrin ")


def _normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).casefold()
    text = text.replace("ي", "ی").replace("ك", "ک").replace("‌", " ")
    text = re.sub(r"[،,؟?!。؛;:.]", " ", text)
    return " ".join(text.split())


class DemoCommandInterpreter:
    """Recognize a few test phrases without claiming general language support."""

    def __init__(self) -> None:
        self._context_resolver = ContextResolver(_CHAT_APPS)

    def interpret(
        self,
        text: str,
        *,
        language: str | None,
        context: CommandContext,
        pending: PendingClarification | None,
    ) -> Interpretation:
        phrase = _normalize(text)
        for prefix in _WAKE_PREFIXES:
            if phrase.startswith(prefix):
                phrase = phrase[len(prefix) :]
                break
        if not phrase or phrase in ("کایرین", "کایری", "kyrin"):
            return NotACommand()

        if pending is not None:
            app = _APPS.get(phrase.removeprefix("در "))
            if app is not None:
                return ReadyCommand(
                    CommandIntent(CommandKind.OPEN_CHAT, pending.target, app)
                )

        # Negation cancels the example command; it must never become "open".
        if "باز نکن" in phrase or phrase.startswith("don't open "):
            return NotACommand()

        match = _OPEN_APP_FA.fullmatch(phrase) or _OPEN_APP_EN.fullmatch(phrase)
        if match is not None:
            return ReadyCommand(CommandIntent(CommandKind.OPEN_APP, _APPS[match[1]]))

        match = _OPEN_CHAT_WITH_APP_FA.fullmatch(phrase)
        if match is not None:
            return ReadyCommand(
                CommandIntent(CommandKind.OPEN_CHAT, match[1], _APPS[match[2]])
            )

        match = (
            _OPEN_CHAT_FA.fullmatch(phrase)
            or _GO_CHAT_FA.fullmatch(phrase)
            or _OPEN_CHAT_EN.fullmatch(phrase)
        )
        if match is not None:
            person = match[1].strip()
            resolution = self._context_resolver.resolve_chat_app(context)
            if not isinstance(resolution, AppClarification):
                return ReadyCommand(
                    CommandIntent(CommandKind.OPEN_CHAT, person, resolution.app)
                )
            if len(resolution.candidates) == 2:
                first, second = resolution.candidates
                app_names = {"telegram": "تلگرام", "whatsapp": "واتساپ"}
                question = (
                    f"چت {person} را در {app_names[first]} باز کنم "
                    f"یا {app_names[second]}؟"
                )
            else:
                question = "چت را در کدام برنامه باز کنم؟"
            return NeedsClarification(PendingClarification(person, question))

        if phrase.startswith(("تلگرام", "مرورگر", "چت ", "به گفتگوی ")):
            return IncompleteCommand()
        if (
            "باز کن" in phrase
            or phrase.endswith("برو")
            or phrase.startswith(("open ", "go to "))
        ):
            return UnrecognizedCommand()
        return NotACommand()
