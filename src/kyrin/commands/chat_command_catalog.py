"""Bounded spoken forms for opening chats, separate from chat-name spelling."""

import re
from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True, slots=True)
class ChatCommandForm:
    scope: Literal["search", "visible"]
    pattern: re.Pattern[str]


@dataclass(frozen=True, slots=True)
class MatchedChatCommand:
    scope: Literal["search", "visible"]
    spoken_target: str


# Put the more specific form first. Only command words may have reviewed STT
# variants; arbitrary chat names are left untouched for screen grounding.
ENGLISH_CHAT_FORMS = (
    ChatCommandForm(
        "visible",
        re.compile(r"^(?:open ?|go to )(?:the )?(?:visible|visibly) chat (.+)$"),
    ),
    ChatCommandForm("search", re.compile(r"^(?:open|go to) chat (.+)$")),
    ChatCommandForm(
        "search",
        re.compile(r"^(?:open|go to) (?:the )?(.+?)(?:'s)? chat$"),
    ),
)


def match_english_chat_command(phrase: str) -> MatchedChatCommand | None:
    """Match a normalized whole command and return its untouched name slot."""
    if phrase in {
        "open visible chat",
        "open visibly chat",
        "openvisible chat",
        "openvisibly chat",
    }:
        return None
    for form in ENGLISH_CHAT_FORMS:
        match = form.pattern.fullmatch(phrase)
        if match is not None and match[1].strip():
            return MatchedChatCommand(form.scope, match[1].strip())
    return None
