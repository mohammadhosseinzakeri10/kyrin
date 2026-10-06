"""Allow only final, explicitly permitted commands to reach an executor."""

from dataclasses import dataclass, field

from kyrin.actions.models import (
    ActionDecision,
    ActionFeedback,
    ActionKey,
    ActionNotice,
    ActionNoticeReason,
    ActionOutcome,
    ActionRequest,
    ActionResult,
)
from kyrin.commands.models import (
    CommandEvent,
    CommandIntent,
    CommandKind,
    CommandResolution,
    ResponseChannel,
    VerifiedContext,
)


@dataclass(frozen=True, slots=True)
class ActionPolicy:
    """Explicit capabilities; an empty policy denies every action."""

    allowed_apps: frozenset[str] = field(default_factory=frozenset)
    allowed_chat_apps: frozenset[str] = field(default_factory=frozenset)
    confirmation_required_for: frozenset[CommandKind] = field(default_factory=frozenset)
    supported_kinds: frozenset[CommandKind] = field(
        default_factory=lambda: frozenset({CommandKind.OPEN_APP, CommandKind.OPEN_CHAT})
    )
    max_pending: int = 32

    def __post_init__(self) -> None:
        if self.max_pending <= 0:
            raise ValueError("max_pending must be positive")
        if any(not app.strip() for app in self.allowed_apps | self.allowed_chat_apps):
            raise ValueError("allowed app identifiers must not be empty")


class ActionGate:
    """Policy state for one ordered command coordinator, without OS access."""

    def __init__(self, policy: ActionPolicy) -> None:
        self.policy = policy
        self._last_key: ActionKey | None = None
        self._awaiting_confirmation: dict[ActionKey, ActionRequest] = {}
        self._outstanding: dict[ActionKey, ActionRequest] = {}
        self._verified_context = VerifiedContext()

    @property
    def verified_context(self) -> VerifiedContext:
        return self._verified_context

    def observe(self, event: CommandEvent) -> ActionDecision | None:
        """Accept one final resolution once; candidates never authorize work."""
        if not isinstance(event, CommandResolution):
            return None
        key = ActionKey(event.stream_id, event.segment_id, event.step_index)
        if self._last_key is not None and key <= self._last_key:
            return None
        self._last_key = key
        intent = event.intent
        if intent is None:
            return None
        if intent.kind not in self.policy.supported_kinds:
            return ActionNotice(
                key, intent, ActionNoticeReason.UNSUPPORTED, language=event.language
            )
        if not self._allowed(intent):
            return ActionNotice(
                key, intent, ActionNoticeReason.NOT_ALLOWED, language=event.language
            )
        if self._pending_count >= self.policy.max_pending:
            return ActionNotice(
                key, intent, ActionNoticeReason.BUSY, language=event.language
            )
        if intent.kind in self.policy.confirmation_required_for:
            self._awaiting_confirmation[key] = ActionRequest(
                key, intent, event.language
            )
            return ActionNotice(
                key,
                intent,
                ActionNoticeReason.CONFIRMATION_REQUIRED,
                language=event.language,
            )
        return self._issue(key, intent, event.language)

    def confirm(self, key: ActionKey, *, approved: bool) -> ActionDecision:
        """Accept an explicit decision from a future trusted confirmation flow."""
        try:
            pending = self._awaiting_confirmation.pop(key)
        except KeyError as exc:
            raise ValueError("no confirmation is pending for this action") from exc
        if not approved:
            return ActionNotice(
                key,
                pending.intent,
                ActionNoticeReason.CANCELLED,
                language=pending.language,
            )
        return self._issue(key, pending.intent, pending.language)

    def record_result(self, result: ActionResult) -> ActionFeedback:
        """Apply a matched result without treating an unverified launch as fact."""
        try:
            request = self._outstanding.pop(result.key)
        except KeyError as exc:
            raise ValueError("result does not match an outstanding action") from exc
        if (
            request.intent.kind is CommandKind.OPEN_APP
            and result.outcome is not ActionOutcome.FAILED
        ):
            self._verified_context = VerifiedContext()
        if (
            result.outcome is ActionOutcome.CONFIRMED
            and result.observed_active_app is not None
        ):
            self._verified_context = VerifiedContext(result.observed_active_app)
        return ActionFeedback(
            result.key,
            request.intent,
            result.outcome,
            ResponseChannel.TEXT_ONLY
            if result.outcome
            in (ActionOutcome.CONFIRMED, ActionOutcome.LAUNCH_ACCEPTED)
            else ResponseChannel.TEXT_AND_VOICE,
            result.error_code,
            request.language,
        )

    @property
    def _pending_count(self) -> int:
        return len(self._awaiting_confirmation) + len(self._outstanding)

    def _allowed(self, intent: CommandIntent) -> bool:
        if intent.kind is CommandKind.OPEN_APP:
            return intent.target in self.policy.allowed_apps
        if intent.kind is CommandKind.OPEN_CHAT:
            return intent.app in self.policy.allowed_chat_apps
        return False

    def _issue(
        self, key: ActionKey, intent: CommandIntent, language: str | None
    ) -> ActionRequest:
        request = ActionRequest(key, intent, language)
        self._outstanding[key] = request
        return request
