"""Tiny offline demonstration interpreter; not the multilingual product engine."""

import re
import unicodedata
from collections.abc import Sequence

from kyrin.commands.app_names import AppNameResolver
from kyrin.commands.context_resolver import (
    AppClarification,
    ContextResolver,
)
from kyrin.commands.interpreter import (
    DeclinedClarification,
    IncompleteCommand,
    Interpretation,
    NeedsClarification,
    NotACommand,
    ReadyCommand,
    ReadyPlan,
    UnrecognizedCommand,
    WakeOnly,
)
from kyrin.commands.models import (
    CommandContext,
    CommandIntent,
    CommandKind,
    CommandPlan,
    PendingAppClarification,
    PendingClarification,
    PendingCommandClarification,
    PendingIntentClarification,
)

_APPS = {
    "تلگرام": "telegram",
    "تلیگرام": "telegram",
    "telegram": "telegram",
    "مرورگر": "browser",
    "browser": "browser",
    "واتساپ": "whatsapp",
    "whatsapp": "whatsapp",
}
_CHAT_APPS = frozenset({"telegram", "whatsapp"})
_OPEN_APP_FA = re.compile(r"^(تلگرام|تلیگرام|مرورگر) را باز کن$")
_OPEN_APP_EN = re.compile(r"^(?:open|go to) (?:the )?(telegram|browser)$")
_OPEN_NAMED_APP_FA = re.compile(r"^(.+?) را باز کن$")
_OPEN_NAMED_APP_EN = re.compile(r"^(?:open|go to) (?:the )?(.+)$")
_WINDOW_COMMAND_EN = re.compile(
    r"^(restore|show|bring back|minimize|close) (?:the )?(.+?)(?: window)?$"
)
_WINDOW_COMMAND_FA = re.compile(r"^(.+?) را (دوباره نشان بده|برگردان|کوچک کن|ببند)$")
_SIZE_COMMAND_EN = re.compile(
    r"^(maximize|unmaximize|fullscreen|exit fullscreen on) (?:the )?(.+?)(?: window)?$"
)
_MAKE_FULLSCREEN_EN = re.compile(r"^make (?:the )?(.+?) fullscreen$")
_SIZE_COMMAND_FA = re.compile(
    r"^(.+?) را (بزرگ کن|به اندازه عادی برگردان|تمام صفحه کن|از تمام صفحه خارج کن)$"
)
_OPEN_APP_CLAUSE_EN = re.compile(r"^(?:open|go to) (?:the )?(.+)$")
_OPEN_CHAT_CLAUSE_EN = re.compile(
    r"^(?:open|go to) (?:the )?(?:chat (.+)|(.+?)(?:'s)? chat)$"
)
_OPEN_CHAT_WITH_APP_FA = re.compile(r"^چت (.+?) را در (تلگرام|واتساپ) باز کن$")
_OPEN_CHAT_FA = re.compile(r"^(?:چت|گفتگوی) (.+?) را باز کن$")
_GO_CHAT_FA = re.compile(r"^به (?:چت|گفتگوی) (.+?) برو$")
_OPEN_CHAT_EN = re.compile(r"^(?:open|go to) chat (.+)$")
_WAKE_PREFIXES = (
    "کایرین",
    "کایری",
    "kyrin",
    "kairin",
    "kyreen",
    "kyrie",
    "kairi",
)


def _normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).casefold()
    text = text.replace("’", "'")
    text = text.replace("ي", "ی").replace("ك", "ک").replace("‌", " ")
    text = re.sub(r"[،,؟?!。؛;:.]", " ", text)
    return " ".join(text.split())


class DemoCommandInterpreter:
    """Recognize a few test phrases without claiming general language support."""

    def __init__(
        self,
        app_name_resolver: AppNameResolver | None = None,
        *,
        wake_aliases: Sequence[str] = (),
    ) -> None:
        self._context_resolver = ContextResolver(_CHAT_APPS)
        self._app_name_resolver = app_name_resolver
        self._wake_prefixes = tuple(
            sorted(
                {
                    normalized
                    for alias in (*_WAKE_PREFIXES, *wake_aliases)
                    if (normalized := _normalize(alias))
                },
                key=len,
                reverse=True,
            )
        )

    def interpret(
        self,
        text: str,
        *,
        language: str | None,
        context: CommandContext,
        pending: PendingCommandClarification | None,
    ) -> Interpretation:
        phrase = _normalize(text)
        addressed = False
        for prefix in self._wake_prefixes:
            if phrase == prefix or phrase.startswith(prefix + " "):
                phrase = phrase[len(prefix) :].strip()
                addressed = True
                break
        if not phrase:
            return WakeOnly() if addressed else NotACommand()

        if isinstance(pending, PendingIntentClarification):
            if phrase in ("no", "cancel", "نه", "خیر", "لغو"):
                return DeclinedClarification()
            if phrase in ("app", "the app", "application", "برنامه", "خود برنامه"):
                return ReadyCommand(
                    CommandIntent(CommandKind.OPEN_APP, pending.app_candidate.app_id)
                )
            if phrase in ("chat", "the chat", "conversation", "چت", "گفتگو"):
                return self._chat_command(
                    pending.chat_target, context, pending.chat_app
                )
            return NeedsClarification(pending)

        if isinstance(pending, PendingAppClarification):
            if phrase in ("no", "نه", "خیر"):
                return DeclinedClarification()
            if pending.confirmation and phrase in ("yes", "بله", "آره"):
                return ReadyCommand(
                    CommandIntent(CommandKind.OPEN_APP, pending.candidates[0].app_id)
                )
            if self._app_name_resolver is not None:
                reply = self._app_name_resolver.resolve(phrase)
                selected = tuple(
                    candidate
                    for candidate in reply.candidates
                    if candidate.app_id in {item.app_id for item in pending.candidates}
                )
                if reply.exact and len(selected) == 1:
                    return ReadyCommand(
                        CommandIntent(CommandKind.OPEN_APP, selected[0].app_id)
                    )
                if phrase in ("yes", "بله", "آره") or (
                    reply.exact and len(selected) > 1
                ):
                    return NeedsClarification(pending)

        if isinstance(pending, PendingClarification):
            app = _APPS.get(phrase.removeprefix("در "))
            if app is not None:
                return ReadyCommand(
                    CommandIntent(CommandKind.OPEN_CHAT, pending.target, app)
                )

        # Negation cancels the example command; it must never become "open".
        if "باز نکن" in phrase or phrase.startswith(("don't open ", "do not open ")):
            return NotACommand()

        size_match = _SIZE_COMMAND_EN.fullmatch(phrase)
        if size_match is not None:
            operation, name = size_match.groups()
            kind = {
                "maximize": CommandKind.MAXIMIZE_APP,
                "unmaximize": CommandKind.UNMAXIMIZE_APP,
                "fullscreen": CommandKind.FULLSCREEN_APP,
                "exit fullscreen on": CommandKind.UNFULLSCREEN_APP,
            }[operation]
            target = self._exact_app(name)
            return (
                ReadyCommand(CommandIntent(kind, target))
                if target is not None
                else UnrecognizedCommand()
            )
        full_match = _MAKE_FULLSCREEN_EN.fullmatch(phrase)
        if full_match is not None:
            target = self._exact_app(full_match[1])
            return (
                ReadyCommand(CommandIntent(CommandKind.FULLSCREEN_APP, target))
                if target is not None
                else UnrecognizedCommand()
            )
        size_match = _SIZE_COMMAND_FA.fullmatch(phrase)
        if size_match is not None:
            name, operation = size_match.groups()
            kind = {
                "بزرگ کن": CommandKind.MAXIMIZE_APP,
                "به اندازه عادی برگردان": CommandKind.UNMAXIMIZE_APP,
                "تمام صفحه کن": CommandKind.FULLSCREEN_APP,
                "از تمام صفحه خارج کن": CommandKind.UNFULLSCREEN_APP,
            }[operation]
            target = self._exact_app(name)
            return (
                ReadyCommand(CommandIntent(kind, target))
                if target is not None
                else UnrecognizedCommand()
            )

        # Window commands require an exact installed app match. A near match
        # must never acquire permission to close an unrelated window.
        window_match = _WINDOW_COMMAND_EN.fullmatch(phrase)
        if window_match is not None:
            operation, name = window_match.groups()
            kind = {
                "restore": CommandKind.RESTORE_APP,
                "show": CommandKind.RESTORE_APP,
                "bring back": CommandKind.RESTORE_APP,
                "minimize": CommandKind.MINIMIZE_APP,
                "close": CommandKind.CLOSE_APP_WINDOW,
            }[operation]
            target = self._exact_app(name)
            return (
                ReadyCommand(CommandIntent(kind, target))
                if target is not None
                else UnrecognizedCommand()
            )
        window_match = _WINDOW_COMMAND_FA.fullmatch(phrase)
        if window_match is not None:
            name, operation = window_match.groups()
            kind = {
                "دوباره نشان بده": CommandKind.RESTORE_APP,
                "برگردان": CommandKind.RESTORE_APP,
                "کوچک کن": CommandKind.MINIMIZE_APP,
                "ببند": CommandKind.CLOSE_APP_WINDOW,
            }[operation]
            target = self._exact_app(name)
            return (
                ReadyCommand(CommandIntent(kind, target))
                if target is not None
                else UnrecognizedCommand()
            )

        if " and " in phrase and phrase.startswith(("open ", "go to ")):
            return self._interpret_english_plan(phrase)

        if self._app_name_resolver is not None:
            app_match = _OPEN_NAMED_APP_FA.fullmatch(
                phrase
            ) or _OPEN_NAMED_APP_EN.fullmatch(phrase)
            explicit_chat_match = _OPEN_CHAT_WITH_APP_FA.fullmatch(phrase)
            chat_match = (
                explicit_chat_match
                or _OPEN_CHAT_FA.fullmatch(phrase)
                or _GO_CHAT_FA.fullmatch(phrase)
                or _OPEN_CHAT_EN.fullmatch(phrase)
            )
            if app_match is not None and chat_match is not None:
                app_result = self._app_name_resolver.resolve(app_match[1])
                if len(app_result.candidates) > 1:
                    return UnrecognizedCommand()
                if len(app_result.candidates) == 1:
                    chat_app = (
                        _APPS[explicit_chat_match[2]]
                        if explicit_chat_match is not None
                        else None
                    )
                    return NeedsClarification(
                        PendingIntentClarification(
                            app_result.candidates[0], chat_match[1].strip(), chat_app
                        )
                    )

        match = _OPEN_CHAT_WITH_APP_FA.fullmatch(phrase)
        if match is not None:
            return self._chat_command(match[1], context, _APPS[match[2]])

        match = (
            _OPEN_CHAT_FA.fullmatch(phrase)
            or _GO_CHAT_FA.fullmatch(phrase)
            or _OPEN_CHAT_EN.fullmatch(phrase)
        )
        if match is not None:
            return self._chat_command(match[1].strip(), context)

        if self._app_name_resolver is not None:
            match = _OPEN_NAMED_APP_FA.fullmatch(
                phrase
            ) or _OPEN_NAMED_APP_EN.fullmatch(phrase)
            if match is not None:
                result = self._app_name_resolver.resolve(match[1])
                if len(result.candidates) == 1 and result.exact:
                    return ReadyCommand(
                        CommandIntent(CommandKind.OPEN_APP, result.candidates[0].app_id)
                    )
                if result.candidates:
                    return NeedsClarification(
                        PendingAppClarification(
                            result.candidates, confirmation=len(result.candidates) == 1
                        )
                    )
                return UnrecognizedCommand()
        else:
            match = _OPEN_APP_FA.fullmatch(phrase) or _OPEN_APP_EN.fullmatch(phrase)
            if match is not None:
                return ReadyCommand(
                    CommandIntent(CommandKind.OPEN_APP, _APPS[match[1]])
                )

        if phrase in ("open", "go to", "باز کن") or phrase.startswith(
            ("تلگرام", "مرورگر", "چت ", "به گفتگوی ")
        ):
            return IncompleteCommand()
        if (
            "باز کن" in phrase
            or phrase.endswith("برو")
            or phrase.startswith(("open ", "go to ", "to open "))
            or addressed
        ):
            return UnrecognizedCommand()
        return NotACommand()

    def _interpret_english_plan(self, phrase: str) -> Interpretation:
        """Recognize two explicit steps; never execute a fragment of unclear text."""
        clauses = phrase.split(" and ")
        if len(clauses) != 2:
            return UnrecognizedCommand()
        first_match = _OPEN_APP_CLAUSE_EN.fullmatch(clauses[0])
        if first_match is None:
            return UnrecognizedCommand()
        first_app = self._exact_app(first_match[1])
        if first_app is None:
            return UnrecognizedCommand()
        if _OPEN_CHAT_CLAUSE_EN.fullmatch(clauses[0]) is not None:
            return UnrecognizedCommand()
        first = CommandIntent(CommandKind.OPEN_APP, first_app)

        chat_match = _OPEN_CHAT_CLAUSE_EN.fullmatch(clauses[1])
        if chat_match is not None:
            second_app_match = _OPEN_APP_CLAUSE_EN.fullmatch(clauses[1])
            if (
                second_app_match is not None
                and self._app_name_resolver is not None
                and self._app_name_resolver.resolve(second_app_match[1]).candidates
            ):
                return UnrecognizedCommand()
            person = (chat_match[1] or chat_match[2]).strip()
            if person:
                return ReadyPlan(
                    CommandPlan(
                        (first, CommandIntent(CommandKind.OPEN_CHAT, person, first_app))
                    )
                )
        app_match = _OPEN_APP_CLAUSE_EN.fullmatch(clauses[1])
        if app_match is not None:
            second_app = self._exact_app(app_match[1])
            if second_app is not None:
                return ReadyPlan(
                    CommandPlan(
                        (first, CommandIntent(CommandKind.OPEN_APP, second_app))
                    )
                )
        return UnrecognizedCommand()

    def _chat_command(
        self, person: str, context: CommandContext, app: str | None = None
    ) -> Interpretation:
        if app is not None:
            return ReadyCommand(CommandIntent(CommandKind.OPEN_CHAT, person, app))
        resolution = self._context_resolver.resolve_chat_app(context)
        if not isinstance(resolution, AppClarification):
            return ReadyCommand(
                CommandIntent(CommandKind.OPEN_CHAT, person, resolution.app)
            )
        return NeedsClarification(PendingClarification(person, resolution.candidates))

    def _exact_app(self, spoken_name: str) -> str | None:
        if self._app_name_resolver is not None:
            result = self._app_name_resolver.resolve(spoken_name)
            if result.exact and len(result.candidates) == 1:
                return result.candidates[0].app_id
            return None
        return _APPS.get(spoken_name)
