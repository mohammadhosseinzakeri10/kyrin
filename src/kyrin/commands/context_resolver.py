"""Resolve an omitted chat app without treating conversation history as focus."""

from collections.abc import Collection
from dataclasses import dataclass

from kyrin.commands.models import CommandContext


@dataclass(frozen=True, slots=True)
class ResolvedApp:
    app: str


@dataclass(frozen=True, slots=True)
class AppClarification:
    candidates: tuple[str, ...] = ()


class ContextResolver:
    """Prefer a fresh supported foreground app; ask if history conflicts."""

    def __init__(self, supported_chat_apps: Collection[str]) -> None:
        self._supported_chat_apps = frozenset(supported_chat_apps)

    def resolve_chat_app(
        self, context: CommandContext
    ) -> ResolvedApp | AppClarification:
        observed = (
            context.observed_active_app
            if context.observed_active_app in self._supported_chat_apps
            else None
        )
        previous = (
            context.last_referenced_app
            if context.last_referenced_app in self._supported_chat_apps
            else None
        )
        if observed is not None and previous is not None and observed != previous:
            return AppClarification((previous, observed))
        if observed is not None:
            return ResolvedApp(observed)
        return AppClarification()
