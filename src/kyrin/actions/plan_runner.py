"""Execute final command plans in order without assuming earlier steps succeeded."""

from collections.abc import Callable

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
    CommandKind,
    CommandPlanResolution,
    CommandResolution,
)


class ActionPlanRunner:
    """Apply policy and execute each step; stop on a block or uncertain result."""

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
        self, resolution: CommandPlanResolution
    ) -> tuple[ActionNotice | ActionFeedback, ...]:
        events: list[ActionNotice | ActionFeedback] = []
        for index, intent in enumerate(resolution.plan.steps):
            key = ActionKey(resolution.stream_id, resolution.segment_id, index)
            if (
                intent.kind is CommandKind.OPEN_CHAT
                and intent.kind in self._gate.policy.supported_kinds
                and (
                    self._observe_active_app is None
                    or self._observe_active_app() != intent.app
                )
            ):
                events.append(
                    ActionNotice(
                        key,
                        intent,
                        ActionNoticeReason.DEPENDENCY_UNVERIFIED,
                        language=resolution.language,
                    )
                )
                break

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
                break
            assert isinstance(decision, ActionRequest)
            result = execute_with_unknown_fallback(self._executor, decision)
            feedback = self._gate.record_result(result)
            events.append(feedback)
            if result.outcome in (ActionOutcome.FAILED, ActionOutcome.UNKNOWN):
                break
        return tuple(events)
