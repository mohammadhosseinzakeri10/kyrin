"""Resolve proposed targets without authorizing or executing an action."""

from collections.abc import Collection
from dataclasses import dataclass
from enum import StrEnum

from kyrin.commands.app_names import AppNameResolver
from kyrin.commands.context_resolver import AppClarification, ContextResolver
from kyrin.commands.models import CommandContext
from kyrin.commands.understanding import (
    RequestedOperation,
    UnderstandingResult,
    UnderstandingStatus,
)


class TargetResolutionStatus(StrEnum):
    RESOLVED = "resolved"
    CLARIFY = "clarify"
    NO_ACTION = "no_action"
    UNSUPPORTED = "unsupported"


@dataclass(frozen=True, slots=True)
class ResolvedTargetStep:
    """A catalog app ID and unmodified chat name, still only a proposal."""

    operation: RequestedOperation
    app_id: str
    target_phrase: str | None = None


@dataclass(frozen=True, slots=True)
class TargetResolution:
    status: TargetResolutionStatus
    steps: tuple[ResolvedTargetStep, ...] = ()
    candidates: tuple[str, ...] = ()
    reason: str | None = None


class SemanticTargetResolver:
    """Check model-proposed names against installed, explicitly allowed apps.

    Neither RESOLVED nor an exact catalog match grants permission. A later
    planner, action gate, and (where needed) confirmation still make that
    decision. System-power proposals never pass through this resolver.
    """

    def __init__(
        self,
        app_names: AppNameResolver,
        *,
        allowed_apps: Collection[str],
        supported_chat_apps: Collection[str],
    ) -> None:
        self._app_names = app_names
        self._allowed_apps = frozenset(allowed_apps)
        self._chat_apps = frozenset(supported_chat_apps) & self._allowed_apps
        self._context = ContextResolver(self._chat_apps)

    def resolve(
        self, result: UnderstandingResult, *, context: CommandContext
    ) -> TargetResolution:
        if (
            result.status is UnderstandingStatus.NOT_COMMAND
            or result.status is UnderstandingStatus.NEGATED
        ):
            return TargetResolution(TargetResolutionStatus.NO_ACTION)
        if result.status is UnderstandingStatus.UNSUPPORTED:
            return TargetResolution(TargetResolutionStatus.UNSUPPORTED)
        if result.status is not UnderstandingStatus.READY:
            return TargetResolution(
                TargetResolutionStatus.CLARIFY, reason=result.status.value
            )

        steps = result.candidates[0].steps
        if len(steps) > 3:
            return TargetResolution(
                TargetResolutionStatus.UNSUPPORTED, reason="plan_too_long"
            )
        resolved: list[ResolvedTargetStep] = []
        for step in steps:
            if step.operation in {
                RequestedOperation.POWER_OFF_SYSTEM,
                RequestedOperation.RESTART_SYSTEM,
                RequestedOperation.LOG_OUT_SYSTEM,
                RequestedOperation.SUSPEND_SYSTEM,
            }:
                return TargetResolution(
                    TargetResolutionStatus.UNSUPPORTED,
                    reason="system_power_requires_separate_flow",
                )

            if (
                step.operation is RequestedOperation.OPEN_CHAT
                and step.app_phrase is None
            ):
                planned_app = (
                    resolved[-1].app_id
                    if resolved
                    and resolved[-1].operation
                    in {RequestedOperation.OPEN_APP, RequestedOperation.RESTORE_APP}
                    and resolved[-1].app_id in self._chat_apps
                    else None
                )
                if planned_app is not None:
                    # The planner must later confirm this earlier step succeeded.
                    app_id = planned_app
                else:
                    app = self._context.resolve_chat_app(context)
                    if isinstance(app, AppClarification):
                        return TargetResolution(
                            TargetResolutionStatus.CLARIFY,
                            candidates=app.candidates,
                            reason="chat_app_context",
                        )
                    app_id = app.app
            else:
                phrase = (
                    step.app_phrase
                    if step.app_phrase is not None
                    else step.target_phrase
                )
                assert phrase is not None  # MeaningStep validates application targets.
                match = self._app_names.resolve(phrase)
                candidates = tuple(
                    dict.fromkeys(
                        candidate.app_id
                        for candidate in match.candidates
                        if candidate.app_id in self._allowed_apps
                        and (
                            step.operation is not RequestedOperation.OPEN_CHAT
                            or candidate.app_id in self._chat_apps
                        )
                    )
                )
                if not match.exact or len(candidates) != 1:
                    return TargetResolution(
                        TargetResolutionStatus.CLARIFY,
                        candidates=candidates,
                        reason="app_name",
                    )
                app_id = candidates[0]
            resolved.append(
                ResolvedTargetStep(
                    step.operation,
                    app_id,
                    step.target_phrase
                    if step.operation is RequestedOperation.OPEN_CHAT
                    else None,
                )
            )
        return TargetResolution(TargetResolutionStatus.RESOLVED, tuple(resolved))
