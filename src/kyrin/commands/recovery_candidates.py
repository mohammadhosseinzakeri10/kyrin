"""Role-aware, English phonetic candidates, independent of model rewrites.

Only control spans are phonemized. App identity is an exact catalog binding;
free chat/search content and visible labels are copied from the original input.
"""

import re
from collections.abc import Callable
from dataclasses import dataclass, replace
from itertools import product
from time import monotonic

from kyrin.commands.app_names import AppNameResolver
from kyrin.commands.choice_numbers import choice_index
from kyrin.commands.models import (
    CommandContext,
    CommandIntent,
    CommandKind,
    PendingCommandClarification,
    PendingOperationClarification,
    PendingWindowSelection,
    RecoveryCandidate,
)
from kyrin.commands.phonetics import english_phonemes, phonetic_similarity
from kyrin.text_normalization import fold_case


@dataclass(frozen=True, slots=True)
class RecoveryContract:
    kind: CommandKind
    roles: str
    requirement: str


# An addition to CommandKind is deliberately not enrolled automatically.
RECOVERY_CONTRACTS = (
    RecoveryContract(CommandKind.OPEN_APP, "operation/app", "exact permitted app"),
    RecoveryContract(
        CommandKind.OPEN_CHAT, "operation/chat/app", "literal chat and app"
    ),
    RecoveryContract(CommandKind.TELEGRAM_VIEW, "operation/view", "known view"),
    RecoveryContract(
        CommandKind.TELEGRAM_SETTINGS, "operation/section", "known section"
    ),
    RecoveryContract(CommandKind.TELEGRAM_SEARCH_FOCUS, "operation/search", "Telegram"),
    RecoveryContract(
        CommandKind.TELEGRAM_SEARCH, "operation/payload", "literal payload"
    ),
    RecoveryContract(
        CommandKind.SCROLL_UP, "operation/direction", "independent direction and focus"
    ),
    RecoveryContract(
        CommandKind.SCROLL_DOWN,
        "operation/direction",
        "independent direction and focus",
    ),
    RecoveryContract(
        CommandKind.VISIBLE_CONTROL, "operation/label/state", "fresh option"
    ),
    RecoveryContract(CommandKind.RESTORE_APP, "operation/app", "exact permitted app"),
    RecoveryContract(CommandKind.MINIMIZE_APP, "operation/app", "exact permitted app"),
    RecoveryContract(
        CommandKind.CLOSE_APP_WINDOW, "operation/app", "exact permitted app"
    ),
    RecoveryContract(CommandKind.MAXIMIZE_APP, "operation/app", "exact permitted app"),
    RecoveryContract(
        CommandKind.UNMAXIMIZE_APP, "operation/app", "exact permitted app"
    ),
    RecoveryContract(
        CommandKind.FULLSCREEN_APP, "operation/app", "exact permitted app"
    ),
    RecoveryContract(
        CommandKind.UNFULLSCREEN_APP, "operation/app", "exact permitted app"
    ),
    RecoveryContract(CommandKind.NEW_APP_WINDOW, "operation/app", "pending app menu"),
    RecoveryContract(CommandKind.NEW_APP_TAB, "operation/app", "pending app menu"),
    RecoveryContract(CommandKind.APP_PREFERENCES, "operation/app", "pending app menu"),
    RecoveryContract(
        CommandKind.SHOW_ALL_WINDOWS, "operation/windows", "desktop collection"
    ),
    RecoveryContract(
        CommandKind.SHOW_APP_WINDOWS, "operation/app/windows", "exact app"
    ),
    RecoveryContract(
        CommandKind.SELECT_APP_WINDOW, "operation/index", "current picker"
    ),
    RecoveryContract(
        CommandKind.CLOSE_SHOWN_WINDOW, "operation/index", "current picker"
    ),
    RecoveryContract(
        CommandKind.HIDE_APP_WINDOWS, "operation/app", "exact app or picker"
    ),
    RecoveryContract(
        CommandKind.SELECT_OPEN_APP_WINDOW, "operation/app", "current picker"
    ),
)


@dataclass(frozen=True, slots=True)
class PhoneticPolicy:
    """Experimental retrieval values, not calibrated intent confidence."""

    minimum_similarity: float = 0.80
    minimum_margin: float = 0.08
    max_candidates: int = 24
    max_text_chars: int = 512

    def __post_init__(self) -> None:
        if (
            not 0 < self.minimum_similarity <= 1
            or not 0 <= self.minimum_margin <= 1
            or self.max_candidates < 1
            or self.max_text_chars < 1
        ):
            raise ValueError("invalid phonetic retrieval policy")


_BLOCKED_CONTROL = re.compile(
    r"\b(?:no|not|never|don't|dont|cannot|can't|without|if|when|or|and|then|up|down|"
    r"type|write|say|quote|for|chat|delete|send|pay|restart|reboot|shutdown|microphone|listening)\b"
    r'|["“”«»;]'
)
_NOT_REQUEST = re.compile(
    r"^(?:the|what|why|how|who|where|when|if|i said|it says|this says)\b"
)
_PAYLOAD_ROLE = re.compile(r"\b(?:for|chat)\b")
_SEQUENCE = re.compile(r"\s+(?:and then|then|and)\s+")
_NON_ACTION_PREFIX = re.compile(
    r"^(?:please\s+)?(?:do not|don't|dont|never|no|type|write|say|quote)\b"
)


def explicit_non_action_role(text: str, language: str | None) -> bool:
    """Only a leading source role; negation inside a search payload is different."""
    return bool(
        (language or "").lower().split("-", 1)[0] == "en"
        and _NON_ACTION_PREFIX.search(fold_case(text).strip())
    )


_APP_CONTROLS = (
    (CommandKind.OPEN_APP, "open", ""),
    (CommandKind.RESTORE_APP, "restore", ""),
    (CommandKind.MINIMIZE_APP, "minimize", ""),
    (CommandKind.CLOSE_APP_WINDOW, "close", ""),
    (CommandKind.MAXIMIZE_APP, "maximize", ""),
    (CommandKind.UNMAXIMIZE_APP, "unmaximize", ""),
    (CommandKind.FULLSCREEN_APP, "fullscreen", ""),
    (CommandKind.UNFULLSCREEN_APP, "exit fullscreen on", ""),
    (CommandKind.SHOW_APP_WINDOWS, "show", "windows"),
    (CommandKind.HIDE_APP_WINDOWS, "hide", "windows"),
)


class PhoneticCandidateGenerator:
    def __init__(
        self,
        names: AppNameResolver,
        *,
        allowed_apps: frozenset[str],
        chat_apps: frozenset[str],
        policy: PhoneticPolicy | None = None,
        phonemize: Callable[[str], str | None] = english_phonemes,
    ) -> None:
        self.names = names
        self.allowed_apps = allowed_apps
        self.chat_apps = chat_apps
        self.policy = policy or PhoneticPolicy()
        self._phonemize = phonemize

    def generate(
        self,
        text: str,
        language: str | None,
        context: CommandContext,
        pending: PendingCommandClarification | None = None,
    ) -> tuple[RecoveryCandidate, ...]:
        if (
            not context.is_final_transcript
            or (language or "").lower().split("-", 1)[0] != "en"
            or not 0 < len(text) <= self.policy.max_text_chars
            or _NOT_REQUEST.search(fold_case(text).strip())
        ):
            return ()
        normalized = fold_case(text).strip().rstrip(".!?")
        normalized = re.sub(r"^please\s+", "", normalized)
        # Never split free content at a conjunction. Each step must independently
        # name its target; later focus cannot be inferred from an earlier step.
        parts = _SEQUENCE.split(normalized)
        if len(parts) > 1 and not _PAYLOAD_ROLE.search(normalized):
            if pending is not None or not 2 <= len(parts) <= 3:
                return ()
            choices = [self.generate(part, language, context) for part in parts]
            if any(not items for items in choices):
                return ()
            plans: list[RecoveryCandidate] = []
            for combination in product(*choices):
                if any(
                    item.target_requires_clarification
                    or item.intent.kind not in {kind for kind, _, _ in _APP_CONTROLS}
                    for item in combination
                ):
                    continue
                plans.append(
                    RecoveryCandidate(
                        combination[0].intent,
                        text,
                        " then ".join(item.control_span for item in combination),
                        " then ".join(item.canonical_control for item in combination),
                        min(item.similarity for item in combination),
                        following=tuple(item.intent for item in combination[1:]),
                    )
                )
                if len(plans) >= self.policy.max_candidates:
                    break
            return tuple(sorted(plans, key=lambda item: item.similarity, reverse=True))
        found: list[RecoveryCandidate] = []

        def add(
            kind: CommandKind,
            target: str,
            control: str,
            canonical: str,
            *,
            app: str | None = None,
            index: int | None = None,
            state: bool | None = None,
            direction: str | None = None,
        ) -> None:
            control = control.strip()
            checked_control = control.rsplit(" ", 1)[0] if direction else control
            if (
                not control
                or len(control) > 64
                or _BLOCKED_CONTROL.search(checked_control)
            ):
                return
            # Exact control spans are also useful independent evidence, but
            # there is no string-similarity fallback when IPA is unavailable.
            left, right = self._phonemize(control), self._phonemize(canonical)
            if left is None or right is None:
                return
            similarity = phonetic_similarity(left, right)
            if direction is not None:
                # Direction is a distinct slot. A good verb cannot compensate
                # for an unsupported direction or an explicit opposite one.
                verb, spoken_direction = control.rsplit(" ", 1)
                canonical_verb, canonical_direction = canonical.rsplit(" ", 1)
                if spoken_direction in {"up", "down"} and spoken_direction != direction:
                    return
                pieces = [
                    self._phonemize(value)
                    for value in (
                        verb,
                        spoken_direction,
                        canonical_verb,
                        canonical_direction,
                    )
                ]
                if any(value is None for value in pieces):
                    return
                a, b, c, d = (value for value in pieces if value is not None)
                similarity = min(phonetic_similarity(a, c), phonetic_similarity(b, d))
            if similarity >= self.policy.minimum_similarity:
                try:
                    intent = CommandIntent(
                        kind, target, app, window_index=index, control_state=state
                    )
                except ValueError:
                    return  # preserve the operation's existing payload constraints
                found.append(
                    RecoveryCandidate(
                        intent,
                        text,
                        control,
                        canonical,
                        similarity,
                    )
                )

        # App names are bound BEFORE any phonetic operation comparison.
        for option in self.names.model_options():
            if option.app_id not in self.allowed_apps:
                continue
            for name in (option.display_name, *option.alternate_names):
                needle = fold_case(name)
                for app_match in re.finditer(
                    r"(?<!\w)" + re.escape(needle) + r"(?!\w)", normalized
                ):
                    before, after = (
                        normalized[: app_match.start()].strip(),
                        normalized[app_match.end() :].strip(),
                    )
                    for kind, prefix, suffix in _APP_CONTROLS:
                        if not suffix and after:
                            continue
                        if suffix and not after:
                            continue
                        control = before + (" " + after if suffix else "")
                        add(
                            kind,
                            option.app_id,
                            control,
                            prefix + (" " + suffix if suffix else ""),
                        )
                    if isinstance(pending, PendingWindowSelection) and pending.all_apps:
                        if not after:
                            add(
                                CommandKind.SELECT_OPEN_APP_WINDOW,
                                option.app_id,
                                before,
                                "select",
                            )

        # A phonetic name is only a proposed identity for a targeted question.
        # Never fold its similarity into the operation score or auto-bind it.
        if (
            not found
            and not _BLOCKED_CONTROL.search(normalized)
            and not _PAYLOAD_ROLE.search(normalized)
        ):
            words = normalized.split()
            for split in range(1, min(4, len(words))):
                control, spoken_name = " ".join(words[:split]), " ".join(words[split:])
                spoken_ipa = self._phonemize(spoken_name)
                if spoken_ipa is None:
                    continue
                for option in self.names.model_options():
                    if option.app_id not in self.allowed_apps:
                        continue
                    name_ipa = self._phonemize(fold_case(option.display_name))
                    if (
                        name_ipa is None
                        or phonetic_similarity(spoken_ipa, name_ipa)
                        < self.policy.minimum_similarity
                    ):
                        continue
                    for kind, canonical, suffix in _APP_CONTROLS:
                        if suffix:
                            continue
                        count_before = len(found)
                        add(kind, option.app_id, control, canonical)
                        if len(found) > count_before:
                            found[-1] = replace(
                                found[-1],
                                source="phonetic_app_name",
                                target_requires_clarification=True,
                            )

        focused = context.observed_scroll_app or context.observed_active_app
        if focused in self.allowed_apps:
            for direction, kind in (
                ("up", CommandKind.SCROLL_UP),
                ("down", CommandKind.SCROLL_DOWN),
            ):
                match = re.fullmatch(r"(.+?)\s+(\w+)", normalized)
                if match:
                    # add() excludes exact direction words from its general
                    # control blocker by checking the verb independently.
                    if not _BLOCKED_CONTROL.search(match[1]):
                        add(
                            kind,
                            focused,
                            normalized,
                            "scroll " + direction,
                            direction=direction,
                        )
        for suffix in ("all windows", "open windows"):
            if normalized.endswith(" " + suffix):
                add(
                    CommandKind.SHOW_ALL_WINDOWS,
                    "desktop",
                    normalized[: -len(suffix)],
                    "show",
                )

        if "telegram" in self.chat_apps and focused == "telegram":
            for label, target in (
                ("archive", "archive"),
                ("contacts", "contacts"),
                ("settings", "settings"),
            ):
                suffix = "telegram " + label
                if normalized.endswith(" " + suffix):
                    add(
                        CommandKind.TELEGRAM_VIEW,
                        target,
                        normalized[: -len(suffix)],
                        "open",
                    )
            suffix = "telegram search"
            if normalized.endswith(" " + suffix):
                add(
                    CommandKind.TELEGRAM_SEARCH_FOCUS,
                    "telegram",
                    normalized[: -len(suffix)],
                    "open",
                )
            match = re.fullmatch(
                r"(.+?)\s+(?:telegram\s+)?for\s+(.+)",
                text.strip(),
                re.IGNORECASE,
            )
            if match:
                # Only the action prefix is converted; payload is verbatim.
                add(
                    CommandKind.TELEGRAM_SEARCH, match[2], fold_case(match[1]), "search"
                )
            match = re.fullmatch(
                r"(.+?)\s+chat\s+(.+?)\s+in\s+telegram", text.strip(), re.IGNORECASE
            )
            if match:
                add(
                    CommandKind.OPEN_CHAT,
                    match[2],
                    fold_case(match[1]),
                    "open",
                    app="telegram",
                )
            match = re.fullmatch(
                r"(.+?)\s+telegram\s+settings\s+(privacy|notifications|devices)",
                normalized,
            )
            if match:
                add(CommandKind.TELEGRAM_SETTINGS, match[2], match[1], "open")

        if isinstance(pending, PendingOperationClarification):
            for kind, canonical in (
                (CommandKind.NEW_APP_WINDOW, "new window"),
                (CommandKind.NEW_APP_TAB, "new tab"),
                (CommandKind.APP_PREFERENCES, "preferences"),
            ):
                if kind in pending.options:
                    add(kind, pending.app_candidate.app_id, normalized, canonical)
        if isinstance(pending, PendingWindowSelection):
            if normalized.isdecimal():
                index = choice_index(normalized, pending.count)
                if index is not None:
                    add(
                        CommandKind.SELECT_APP_WINDOW,
                        pending.app_candidate.app_id,
                        "select",
                        "select",
                        index=index + 1,
                    )
            match = re.fullmatch(r"(.+?)\s+(?:number\s+)?([0-9]+)", normalized)
            if match:
                index = choice_index(match[2], pending.count)
                if index is not None:
                    add(
                        CommandKind.CLOSE_SHOWN_WINDOW,
                        pending.app_candidate.app_id,
                        match[1],
                        "close",
                        index=index + 1,
                    )
            add(
                CommandKind.HIDE_APP_WINDOWS,
                pending.app_candidate.app_id,
                normalized,
                "cancel",
            )
        if context.visible_control_enabled and context.observed_scroll_app:
            for visible_option in context.visible_options:
                observation = visible_option.observation
                if (
                    observation is None
                    or observation.app_id != context.observed_scroll_app
                    or not observation.observed_at <= monotonic() < observation.deadline
                ):
                    continue
                suffix = fold_case(visible_option.label)
                if normalized.endswith(" " + suffix):
                    control = normalized[: -len(suffix)].strip()
                    if not _BLOCKED_CONTROL.search(control):
                        for canonical, desired in (
                            ("click", None),
                            ("enable", True),
                            ("disable", False),
                            ("turn on", True),
                            ("turn off", False),
                            ("check", True),
                            ("uncheck", False),
                        ):
                            if desired is not None and visible_option.checked is None:
                                continue
                            count_before = len(found)
                            add(
                                CommandKind.VISIBLE_CONTROL,
                                visible_option.label,
                                control,
                                canonical,
                                state=desired,
                            )
                            if len(found) == count_before:
                                continue
                            candidate = found[-1]
                            found[-1] = replace(
                                candidate,
                                intent=replace(
                                    candidate.intent,
                                    control_source=visible_option.source,
                                    control_accessibility=visible_option.accessibility,
                                    control_anchor=visible_option.anchor,
                                    control_observation=visible_option.observation,
                                    control_window_app=context.observed_scroll_app,
                                ),
                            )
        unique: dict[CommandIntent, RecoveryCandidate] = {}
        for candidate in found:
            if (
                candidate.intent not in unique
                or unique[candidate.intent].similarity < candidate.similarity
            ):
                unique[candidate.intent] = candidate
        return tuple(
            sorted(unique.values(), key=lambda c: c.similarity, reverse=True)[
                : self.policy.max_candidates
            ]
        )
