"""Execute final command plans in order without assuming earlier steps succeeded."""

from collections.abc import Callable

from kyrin.actions.cancellation import ActionCancelled, ActionExecutionContext
from kyrin.actions.executor import ActionExecutor, execute_with_unknown_fallback
from kyrin.actions.gate import ActionGate
from kyrin.actions.models import (
    ActionFeedback,
    ActionKey,
    ActionNotice,
    ActionNoticeReason,
    ActionOutcome,
    ActionRequest,
)
from kyrin.commands.models import (
    CommandIntent,
    CommandKind,
    CommandPlanResolution,
    CommandResolution,
)
from kyrin.timing import mark


class ActionPlanRunner:
    """Require verified prerequisites; independent app launches may continue.

    Focus-based steps conservatively depend on earlier steps. Opening a different
    named app is independent. Repeating the same unverified launch is a retry,
    not an independent step, and cannot resend input without new observation.
    """

    def __init__(
        self,
        gate: ActionGate,
        executor: ActionExecutor,
        *,
        observe_active_app: Callable[[], str | None] | None = None,
    ) -> None:
        self._gate = gate
        self._executor = executor
        self._observe_active_app = observe_active_app

    def run(
        self,
        resolution: CommandPlanResolution,
        *,
        context: ActionExecutionContext | None = None,
    ) -> tuple[ActionNotice | ActionFeedback, ...]:
        events: list[ActionNotice | ActionFeedback] = []
        unverified: list[CommandIntent] = []
        for index, intent in enumerate(resolution.plan.steps):
            key = ActionKey(resolution.stream_id, resolution.segment_id, index)
            if context is not None and context.cancelled:
                events.append(
                    ActionNotice(
                        key,
                        intent,
                        ActionNoticeReason.CANCELLED,
                        language=resolution.language,
                    )
                )
                break
            active_app = (
                self._observe_active_app()
                if intent.kind is CommandKind.OPEN_CHAT
                and intent.kind in self._gate.policy.supported_kinds
                and self._observe_active_app is not None
                else None
            )
            decision = self._gate.observe(
                CommandResolution(
                    resolution.segment_id,
                    intent,
                    stream_id=resolution.stream_id,
                    language=resolution.language,
                    step_index=index,
                )
            )
            if decision is None:
                break
            if isinstance(decision, ActionNotice):
                events.append(decision)
                unverified.append(intent)
                continue
            if any(
                (intent.kind is not CommandKind.OPEN_APP or earlier == intent)
                and not (
                    earlier.kind is CommandKind.OPEN_APP
                    and earlier.target == active_app
                )
                for earlier in unverified
            ) or (
                intent.kind is CommandKind.OPEN_CHAT
                and intent.kind in self._gate.policy.supported_kinds
                and active_app != intent.app
            ):
                self._gate.cancel_unstarted(key)
                events.append(
                    ActionNotice(
                        key,
                        intent,
                        ActionNoticeReason.DEPENDENCY_UNVERIFIED,
                        language=resolution.language,
                    )
                )
                unverified.append(intent)
                continue

            assert isinstance(decision, ActionRequest)
            if context is not None and context.cancelled:
                events.append(self._gate.cancel_unstarted(decision.key))
                break
            try:
                result = execute_with_unknown_fallback(
                    self._executor, decision, context=context
                )
            except ActionCancelled:
                events.append(self._gate.cancel_unstarted(decision.key))
                break
            feedback = self._gate.record_result(result)
            mark("feedback", key=feedback.key)
            if result.outcome is ActionOutcome.CONFIRMED:
                mark("postcondition_observed", key=feedback.key)
            events.append(feedback)
            if result.outcome is not ActionOutcome.CONFIRMED:
                unverified.append(intent)
        return tuple(events)
