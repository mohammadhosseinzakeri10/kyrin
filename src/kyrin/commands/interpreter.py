"""Replaceable semantic interpretation contract, independent of STT backends."""

from dataclasses import dataclass
from typing import Protocol

from kyrin.commands.models import CommandContext, CommandIntent, PendingClarification


@dataclass(frozen=True, slots=True)
class ReadyCommand:
    intent: CommandIntent


@dataclass(frozen=True, slots=True)
class NeedsClarification:
    pending: PendingClarification


@dataclass(frozen=True, slots=True)
class IncompleteCommand:
    """The text looks like an unfinished command."""


@dataclass(frozen=True, slots=True)
class UnrecognizedCommand:
    """The text looks like a command, but cannot be interpreted safely."""


@dataclass(frozen=True, slots=True)
class NotACommand:
    """Ordinary or unrelated speech should not trigger a response."""


Interpretation = (
    ReadyCommand
    | NeedsClarification
    | IncompleteCommand
    | UnrecognizedCommand
    | NotACommand
)


class CommandInterpreter(Protocol):
    def interpret(
        self,
        text: str,
        *,
        language: str | None,
        context: CommandContext,
        pending: PendingClarification | None,
    ) -> Interpretation: ...
