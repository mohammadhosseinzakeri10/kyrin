"""Tiny offline demonstration interpreter; not the multilingual product engine."""

import re
import unicodedata
from collections.abc import Sequence
from difflib import SequenceMatcher

from kyrin.commands.app_names import AppNameResolver, SpokenAppCandidate
from kyrin.commands.choice_numbers import choice_index
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
    PendingActionConfirmation,
    PendingAppClarification,
    PendingClarification,
    PendingCommandClarification,
    PendingIntentClarification,
    PendingNumberedCloseConfirmation,
    PendingOperationClarification,
    PendingWindowSelection,
)
from kyrin.commands.open_window_meaning import requests_open_window_overview
from kyrin.commands.wake_names import DEFAULT_WAKE_NAMES
from kyrin.desktop.window_presence import AppWindowPresence, WindowPresence

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
_OPEN_APP_EN = re.compile(
    r"^(?:please )?(?:open|go to|launch|start|switch to) "
    r"(?:the )?(telegram|browser)$"
)
_OPEN_NAMED_APP_FA = re.compile(r"^(.+?) (?:را|رو) (?:باز|اجرا) کن$")
_OPEN_APP_SUGGESTION_FA = re.compile(r"^(.+?)(?: را| رو)? باز کن$")
_UNCERTAIN_OPEN_FA = re.compile(r"^(.+?) (?:را|رو) (.+)$")
_OPEN_NAMED_APP_EN = re.compile(
    r"^(?:please )?(?:open|go to|launch|start|switch to) (?:the )?(.+)$"
)
_OPEN_ASR_SPELLING = re.compile(r"^(اوپن|اپن|أوبین|opend) (.+)$")
_WINDOW_COMMAND_EN = re.compile(
    r"^(?:(?:please|kindly|gently) )?"
    r"(restore|show|bring back|minimize|hide|close|exit|quit) "
    r"(?:the )?(.+?)(?: window)?$"
)
_WINDOW_COMMAND_FA = re.compile(
    r"^(.+?) (?:را|رو) (دوباره نشان بده|نشان بده|برگردان|کوچک کن|پنهان کن|ببند)$"
)
_BRING_TO_FRONT_EN = re.compile(r"^(?:please )?bring (?:the )?(.+?) to (?:the )?front$")
_SMALLER_EN = re.compile(r"^(?:please )?make (?:the )?(.+?) smaller(?: than now)?$")
_SMALLER_FA = re.compile(r"^(.+?) (?:را|رو) کوچک تر کن$")
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
_WAKE_PREFIXES = (*DEFAULT_WAKE_NAMES, "کایری")
_NUMBERED_CLOSE_EN = re.compile(
    r"^(?:please )?(?:(?:close|exit|quit) (.+)|(.+) (?:close|exit|quit))$"
)
_NUMBERED_CLOSE_FA = re.compile(
    r"^(?:(.+?)(?: (?:را|رو))? ببند|ببند (.+))$"
)


def _close_window_index(text: str, count: int) -> int | None:
    """Accept optional window words, but require one exact menu number."""
    answer = text.strip()
    for prefix in ("the window ", "window ", "the ", "پنجره "):
        if answer.startswith(prefix):
            answer = answer[len(prefix):]
            break
    for suffix in (" window", " پنجره"):
        if answer.endswith(suffix):
            answer = answer[:-len(suffix)]
            break
    return choice_index(answer, count)


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
        browser_candidates: Sequence[SpokenAppCandidate] = (),
        allowed_window_apps: frozenset[str] = frozenset(),
        allowed_close_apps: frozenset[str] = frozenset(),
        window_presence: AppWindowPresence | None = None,
        terminal_app_id: str | None = None,
    ) -> None:
        self._context_resolver = ContextResolver(_CHAT_APPS)
        self._app_name_resolver = app_name_resolver
        self._browser_candidates = tuple(browser_candidates)
        self._allowed_window_apps = allowed_window_apps
        self._allowed_close_apps = allowed_close_apps
        self._window_presence = window_presence
        self._terminal_app_id = terminal_app_id
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

        # A later explicit "do not open" also withdraws a pending app suggestion.
        # Otherwise a still-pending "yes" could act on the older request.
        if "باز نکن" in phrase or phrase.startswith(("don't open ", "do not open ")):
            return DeclinedClarification() if pending is not None else NotACommand()

        if isinstance(pending, PendingActionConfirmation):
            if phrase in ("no", "nein", "نه", "خیر", "لغو", "cancel"):
                return DeclinedClarification()
            if phrase in ("yes", "ja", "بله", "آره"):
                return ReadyCommand(
                    CommandIntent(pending.operation, pending.app_candidate.app_id)
                )
            return NeedsClarification(pending)

        if isinstance(pending, PendingNumberedCloseConfirmation):
            if phrase in ("لغو", "cancel"):
                return ReadyCommand(CommandIntent(
                    CommandKind.HIDE_APP_WINDOWS, pending.app_candidate.app_id
                ))
            if phrase in ("no", "nein", "نه", "خیر"):
                return NeedsClarification(PendingWindowSelection(
                    pending.app_candidate, pending.count, pending.all_apps
                ))
            if phrase in ("yes", "ja", "بله", "آره"):
                return ReadyCommand(CommandIntent(
                    CommandKind.CLOSE_SHOWN_WINDOW,
                    pending.app_candidate.app_id,
                    window_index=pending.window_index,
                ))
            return NeedsClarification(pending)

        if isinstance(pending, PendingWindowSelection):
            if phrase in ("no", "نه", "خیر", "لغو", "cancel"):
                return ReadyCommand(
                    CommandIntent(
                        CommandKind.HIDE_APP_WINDOWS, pending.app_candidate.app_id
                    )
                )
            close_match = _NUMBERED_CLOSE_EN.fullmatch(phrase)
            if close_match is None:
                close_match = _NUMBERED_CLOSE_FA.fullmatch(phrase)
            if close_match is not None:
                number_text = next(
                    (part for part in close_match.groups() if part is not None), ""
                )
                close_index = _close_window_index(number_text, pending.count)
                if close_index is not None:
                    return NeedsClarification(PendingNumberedCloseConfirmation(
                        pending.app_candidate, close_index + 1,
                        pending.count, pending.all_apps,
                    ))
                return NeedsClarification(pending)
            index = choice_index(phrase, pending.count)
            if index is None:
                if pending.all_apps and self._app_name_resolver is not None:
                    named = phrase.removeprefix("go to ").removeprefix("switch to ")
                    app_reply = self._app_name_resolver.resolve(named)
                    if (
                        app_reply.exact
                        and len(app_reply.candidates) == 1
                        and app_reply.candidates[0].app_id
                        in self._allowed_window_apps
                    ):
                        return ReadyCommand(CommandIntent(
                            CommandKind.SELECT_OPEN_APP_WINDOW,
                            app_reply.candidates[0].app_id,
                        ))
                if phrase.startswith(
                    ("open ", "go to ", "close ", "restore ", "minimize ")
                ):
                    return self.interpret(
                        text, language=language, context=context, pending=None
                    )
                return NeedsClarification(pending)
            return ReadyCommand(
                CommandIntent(
                    CommandKind.SELECT_APP_WINDOW,
                    pending.app_candidate.app_id,
                    window_index=index + 1,
                )
            )

        if self._allowed_window_apps and requests_open_window_overview(text, language):
            return self.review_model_action(
                CommandIntent(CommandKind.SHOW_ALL_WINDOWS, "desktop"), context
            )

        if isinstance(pending, PendingOperationClarification):
            if phrase in ("no", "نه", "خیر", "لغو", "cancel"):
                return DeclinedClarification()
            if phrase in ("yes", "ja", "بله", "آره"):
                if CommandKind.OPEN_APP in pending.options:
                    return ReadyCommand(CommandIntent(
                        CommandKind.OPEN_APP, pending.app_candidate.app_id
                    ))
                return NeedsClarification(pending)
            index = choice_index(phrase, len(pending.options))
            selected_operation = pending.options[index] if index is not None else {
                "open": CommandKind.OPEN_APP,
                "باز کن": CommandKind.OPEN_APP,
                "minimize": CommandKind.MINIMIZE_APP,
                "hide": CommandKind.MINIMIZE_APP,
                "کوچک کن": CommandKind.MINIMIZE_APP,
                "close": CommandKind.CLOSE_APP_WINDOW,
                "ببند": CommandKind.CLOSE_APP_WINDOW,
                "normal size": CommandKind.UNMAXIMIZE_APP,
                "restore size": CommandKind.UNMAXIMIZE_APP,
                "اندازه عادی": CommandKind.UNMAXIMIZE_APP,
                "new window": CommandKind.NEW_APP_WINDOW,
                "new tab": CommandKind.NEW_APP_TAB,
                "preferences": CommandKind.APP_PREFERENCES,
                "all windows": CommandKind.SHOW_ALL_WINDOWS,
                "terminal windows": CommandKind.SHOW_APP_WINDOWS,
            }.get(phrase)
            if selected_operation not in pending.options:
                return NeedsClarification(pending)
            if selected_operation is CommandKind.CLOSE_APP_WINDOW:
                return NeedsClarification(
                    PendingActionConfirmation(pending.app_candidate, selected_operation)
                )
            if selected_operation is CommandKind.SHOW_APP_WINDOWS:
                count = (
                    self._window_presence.count(pending.app_candidate.app_id)
                    if self._window_presence is not None
                    else None
                )
                if count is None or count < 2:
                    return NeedsClarification(pending)
                return ReadyCommand(
                    CommandIntent(selected_operation, pending.app_candidate.app_id),
                    PendingWindowSelection(pending.app_candidate, count),
                )
            return ReadyCommand(
                CommandIntent(selected_operation, pending.app_candidate.app_id)
            )

        if isinstance(pending, PendingIntentClarification):
            if phrase in ("no", "cancel", "نه", "خیر", "لغو"):
                return DeclinedClarification()
            selected = choice_index(phrase, 2)
            if selected == 0 or phrase in (
                "app", "the app", "application", "برنامه", "خود برنامه"
            ):
                return ReadyCommand(
                    CommandIntent(CommandKind.OPEN_APP, pending.app_candidate.app_id)
                )
            if selected == 1 or phrase in (
                "chat", "the chat", "conversation", "چت", "گفتگو"
            ):
                return self._chat_command(
                    pending.chat_target, context, pending.chat_app
                )
            return NeedsClarification(pending)

        if isinstance(pending, PendingAppClarification):
            if phrase in ("no", "nein", "نه", "خیر"):
                return DeclinedClarification()
            if pending.confirmation and phrase in ("yes", "ja", "بله", "آره"):
                return self._selected_app(pending.candidates[0], pending, context)
            index = choice_index(phrase, len(pending.candidates))
            if index is not None:
                return self._selected_app(pending.candidates[index], pending, context)
            if self._app_name_resolver is not None:
                reply = self._app_name_resolver.resolve(phrase)
                matching_candidates = tuple(
                    candidate
                    for candidate in reply.candidates
                    if candidate.app_id in {item.app_id for item in pending.candidates}
                )
                if reply.exact and len(matching_candidates) == 1:
                    return self._selected_app(matching_candidates[0], pending, context)
                if phrase in ("yes", "ja", "بله", "آره") or (
                    reply.exact and len(matching_candidates) > 1
                ):
                    return NeedsClarification(pending)

        if isinstance(pending, PendingClarification):
            app = _APPS.get(phrase.removeprefix("در "))
            if app is not None:
                return ReadyCommand(
                    CommandIntent(CommandKind.OPEN_CHAT, pending.target, app)
                )

        # Reviewed ASR spellings of the English verb "open". The app name
        # still has to resolve to one registered application; uncertain Latin
        # "opend" always asks rather than acting on a spelling correction.
        phonetic_open = _OPEN_ASR_SPELLING.fullmatch(phrase)
        if phonetic_open is not None and self._app_name_resolver is not None:
            spelling, name = phonetic_open.groups()
            app_name_match = self._app_name_resolver.resolve(name)
            if (
                app_name_match.exact
                and len(app_name_match.candidates) == 1
                and spelling != "opend"
            ):
                if app_name_match.candidates[0].app_id == self._terminal_app_id:
                    return self._ask_terminal_open(
                        app_name_match.candidates[0], context
                    )
                return ReadyCommand(
                    CommandIntent(
                        CommandKind.OPEN_APP, app_name_match.candidates[0].app_id
                    )
                )
            candidates = app_name_match.candidates or self._app_name_resolver.suggest(
                name
            ).candidates
            if candidates:
                return NeedsClarification(
                    PendingAppClarification(
                        candidates, confirmation=len(candidates) == 1
                    )
                )
            return UnrecognizedCommand()

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
                self._review_window_action(kind, target)
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
                self._review_window_action(kind, target)
                if target is not None
                else UnrecognizedCommand()
            )

        smaller_match = _SMALLER_EN.fullmatch(phrase) or _SMALLER_FA.fullmatch(phrase)
        if smaller_match is not None and self._app_name_resolver is not None:
            resolved_smaller_app = self._app_name_resolver.resolve(smaller_match[1])
            if resolved_smaller_app.exact and len(resolved_smaller_app.candidates) == 1:
                candidate = resolved_smaller_app.candidates[0]
                if candidate.app_id in self._allowed_window_apps:
                    return NeedsClarification(PendingOperationClarification(
                        candidate,
                        (CommandKind.MINIMIZE_APP, CommandKind.UNMAXIMIZE_APP),
                    ))
            return UnrecognizedCommand()

        bring_match = _BRING_TO_FRONT_EN.fullmatch(phrase)
        if bring_match is not None:
            target = self._exact_app(bring_match[1])
            return (
                self._review_window_action(CommandKind.RESTORE_APP, target)
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
                "hide": CommandKind.MINIMIZE_APP,
                "close": CommandKind.CLOSE_APP_WINDOW,
                "exit": CommandKind.CLOSE_APP_WINDOW,
                "quit": CommandKind.CLOSE_APP_WINDOW,
            }[operation]
            target = self._exact_app(name)
            if target is not None:
                return self._review_window_action(kind, target)
            if self._app_name_resolver is not None:
                suggestions = self._app_name_resolver.suggest(name).candidates
                if suggestions:
                    return NeedsClarification(
                        PendingAppClarification(
                            suggestions,
                            confirmation=len(suggestions) == 1,
                            operation=kind,
                        )
                    )
            return UnrecognizedCommand()
        window_match = _WINDOW_COMMAND_FA.fullmatch(phrase)
        if window_match is not None:
            name, operation = window_match.groups()
            kind = {
                "دوباره نشان بده": CommandKind.RESTORE_APP,
                "نشان بده": CommandKind.RESTORE_APP,
                "برگردان": CommandKind.RESTORE_APP,
                "کوچک کن": CommandKind.MINIMIZE_APP,
                "پنهان کن": CommandKind.MINIMIZE_APP,
                "ببند": CommandKind.CLOSE_APP_WINDOW,
            }[operation]
            target = self._exact_app(name)
            return (
                self._review_window_action(kind, target)
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
                    if result.candidates[0].app_id == self._terminal_app_id:
                        return self._ask_terminal_open(result.candidates[0], context)
                    return ReadyCommand(
                        CommandIntent(CommandKind.OPEN_APP, result.candidates[0].app_id)
                    )
                if match[1] in {"browser", "مرورگر"} and self._browser_candidates:
                    return NeedsClarification(
                        PendingAppClarification(
                            self._browser_candidates,
                            confirmation=len(self._browser_candidates) == 1,
                        )
                    )
                if result.candidates:
                    return NeedsClarification(
                        PendingAppClarification(
                            result.candidates, confirmation=len(result.candidates) == 1
                        )
                    )
                suggestion = self._app_name_resolver.suggest(match[1])
                if suggestion.candidates:
                    return NeedsClarification(
                        PendingAppClarification(
                            suggestion.candidates,
                            confirmation=len(suggestion.candidates) == 1,
                        )
                    )
                return UnrecognizedCommand()
            # Without an explicit case marker, a plausible app name remains
            # a suggestion even when it matches exactly.
            suggestion_match = _OPEN_APP_SUGGESTION_FA.fullmatch(phrase)
            if suggestion_match is not None:
                result = self._app_name_resolver.suggest(suggestion_match[1])
                if result.candidates:
                    return NeedsClarification(
                        PendingAppClarification(
                            result.candidates, confirmation=len(result.candidates) == 1
                        )
                    )
                return UnrecognizedCommand()
            # An uncertain operation can request repetition but cannot become
            # an executable open command through fuzzy matching.
            uncertain = _UNCERTAIN_OPEN_FA.fullmatch(phrase)
            if uncertain is not None:
                operation = uncertain[2]
                if (
                    SequenceMatcher(None, operation.replace(" ", ""), "بازکن")
                    .ratio()
                    >= 0.60
                ):
                    return UnrecognizedCommand()

            # A bare application name identifies a target, not an operation.
            if len(phrase.split()) <= 4:
                bare = self._app_name_resolver.resolve(phrase)
                if bare.exact and len(bare.candidates) == 1:
                    return self._ask_operation(bare.candidates[0], context)
                if not bare.exact and (addressed or len(phrase.split()) == 1):
                    suggestions = self._app_name_resolver.suggest(phrase).candidates
                    if suggestions:
                        return NeedsClarification(
                            PendingAppClarification(
                                suggestions,
                                confirmation=len(suggestions) == 1,
                                operation=None,
                            )
                        )
        else:
            match = _OPEN_APP_FA.fullmatch(phrase) or _OPEN_APP_EN.fullmatch(phrase)
            if match is not None:
                return ReadyCommand(
                    CommandIntent(CommandKind.OPEN_APP, _APPS[match[1]])
                )

        if phrase in (
            "open", "go to", "close", "exit", "quit", "باز کن"
        ) or phrase.startswith(
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

    def _selected_app(
        self,
        candidate: SpokenAppCandidate,
        pending: PendingAppClarification,
        context: CommandContext,
    ) -> Interpretation:
        if pending.operation is None or (
            pending.operation is CommandKind.OPEN_APP
            and candidate.app_id == self._terminal_app_id
        ):
            return self._ask_operation(candidate, context)
        return ReadyCommand(CommandIntent(pending.operation, candidate.app_id))

    def _ask_operation(
        self, candidate: SpokenAppCandidate, context: CommandContext
    ) -> Interpretation:
        if candidate.app_id == self._terminal_app_id:
            return self._ask_terminal_open(candidate, context)
        options = [CommandKind.OPEN_APP]
        presence = (
            self._window_presence.observe(candidate.app_id)
            if self._window_presence is not None and context.is_final_transcript
            else WindowPresence.UNKNOWN
        )
        if (
            presence is WindowPresence.OPEN
            or context.observed_active_app == candidate.app_id
        ):
            if candidate.app_id in self._allowed_window_apps:
                options.append(CommandKind.MINIMIZE_APP)
            if candidate.app_id in self._allowed_close_apps:
                options.append(CommandKind.CLOSE_APP_WINDOW)
        return NeedsClarification(
            PendingOperationClarification(candidate, tuple(options))
        )

    def _ask_terminal_open(
        self, candidate: SpokenAppCandidate, context: CommandContext
    ) -> Interpretation:
        if self._window_presence is None or not context.is_final_transcript:
            return NeedsClarification(
                PendingOperationClarification(candidate, (CommandKind.OPEN_APP,))
            )
        count = self._window_presence.count(candidate.app_id)
        if count == 0:
            return ReadyCommand(CommandIntent(CommandKind.OPEN_APP, candidate.app_id))
        if count is None:
            return NeedsClarification(
                PendingOperationClarification(candidate, (CommandKind.OPEN_APP,))
            )
        options = (
            [CommandKind.OPEN_APP]
            if count == 1
            else [CommandKind.SHOW_APP_WINDOWS]
            if candidate.app_id in self._allowed_window_apps
            else []
        )
        options.append(CommandKind.NEW_APP_WINDOW)
        if count == 1:
            options.append(CommandKind.NEW_APP_TAB)
        options.append(CommandKind.APP_PREFERENCES)
        return NeedsClarification(
            PendingOperationClarification(candidate, tuple(options))
        )

    def _review_window_action(
        self, kind: CommandKind, target: str
    ) -> Interpretation:
        if kind is CommandKind.CLOSE_APP_WINDOW and target == self._terminal_app_id:
            return NeedsClarification(
                PendingActionConfirmation(
                    SpokenAppCandidate(target, "Terminal"), kind
                )
            )
        return ReadyCommand(CommandIntent(kind, target))

    def review_model_action(
        self, intent: CommandIntent, context: CommandContext
    ) -> Interpretation:
        """Keep model-proposed Terminal actions on the same safety path."""
        if intent.kind is CommandKind.SHOW_ALL_WINDOWS:
            if intent.target != "desktop" or not self._allowed_window_apps:
                return UnrecognizedCommand()
            return ReadyCommand(
                intent,
                PendingWindowSelection(
                    SpokenAppCandidate("desktop", "open applications"),
                    99, all_apps=True,
                ),
            )
        if (
            intent.kind is CommandKind.OPEN_APP
            and intent.target == self._terminal_app_id
        ):
            return self._ask_terminal_open(
                SpokenAppCandidate(intent.target, "Terminal"), context
            )
        if intent.kind is CommandKind.CLOSE_APP_WINDOW:
            return self._review_window_action(intent.kind, intent.target)
        return ReadyCommand(intent)
