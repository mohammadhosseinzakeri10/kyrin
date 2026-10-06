"""Replaceable semantic interpretation contract, independent of STT backends."""

from dataclasses import dataclass
from typing import Protocol

from kyrin.commands.models import (
    CommandContext,
    CommandIntent,
    CommandPlan,
    PendingAppClarification,
    PendingClarification,
)


@dataclass(frozen=True, slots=True)
class ReadyCommand:
    intent: CommandIntent


@dataclass(frozen=True, slots=True)
class ReadyPlan:
    plan: CommandPlan


@dataclass(frozen=True, slots=True)
class NeedsClarification:
    pending: PendingClarification | PendingAppClarification


@dataclass(frozen=True, slots=True)
class DeclinedClarification:
    """The user rejected a proposed application; clear the pending question."""


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
    | ReadyPlan
    | NeedsClarification
    | DeclinedClarification
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
        pending: PendingClarification | PendingAppClarification | None,
    ) -> Interpretation: ...
