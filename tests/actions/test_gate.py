"""Only allowed final commands may become requests for a future executor."""

import pytest

from kyrin.actions.gate import ActionGate, ActionPolicy
from kyrin.actions.models import (
    ActionFeedback,
    ActionKey,
    ActionNotice,
    ActionNoticeReason,
    ActionOutcome,
    ActionRequest,
    ActionResult,
)
from kyrin.commands.coordinator import CommandCoordinator
from kyrin.commands.demo_interpreter import DemoCommandInterpreter
from kyrin.commands.models import (
    CommandCandidateUpdate,
    CommandIntent,
    CommandKind,
    CommandResolution,
    ResponseChannel,
    VerifiedContext,
)
from kyrin.stt.transcript import TranscriptStatus, TranscriptUpdate

TELEGRAM = CommandIntent(CommandKind.OPEN_APP, "telegram")
BROWSER = CommandIntent(CommandKind.OPEN_APP, "browser")
ALI_CHAT = CommandIntent(CommandKind.OPEN_CHAT, "علی", "telegram")
POLICY = ActionPolicy(
    allowed_apps=frozenset({"telegram", "browser"}),
    allowed_chat_apps=frozenset({"telegram"}),
)


def test_candidate_never_issues_action_and_final_issues_once() -> None:
    gate = ActionGate(POLICY)
    key = ActionKey(0, 4)

    assert gate.observe(CommandCandidateUpdate(4, TELEGRAM)) is None
    assert gate.verified_context == VerifiedContext()
    assert gate.observe(CommandResolution(4, TELEGRAM)) == ActionRequest(key, TELEGRAM)
    assert gate.observe(CommandResolution(4, TELEGRAM)) is None
    assert gate.verified_context == VerifiedContext()

    assert gate.record_result(
        ActionResult(key, ActionOutcome.CONFIRMED, "telegram")
    ) == ActionFeedback(
        key, TELEGRAM, ActionOutcome.CONFIRMED, ResponseChannel.TEXT_ONLY
    )
    assert gate.verified_context == VerifiedContext(active_app="telegram")
    with pytest.raises(ValueError, match="outstanding"):
        gate.record_result(ActionResult(key, ActionOutcome.CONFIRMED, "telegram"))


def test_retracted_or_revised_candidate_uses_only_final_intent() -> None:
    gate = ActionGate(POLICY)
    gate.observe(CommandCandidateUpdate(0, TELEGRAM))
    gate.observe(CommandCandidateUpdate(0, None))
    assert gate.observe(CommandResolution(0, None)) is None

    gate.observe(CommandCandidateUpdate(1, TELEGRAM))
    assert gate.observe(CommandResolution(1, BROWSER)) == ActionRequest(
        ActionKey(0, 1), BROWSER
    )


def test_unknown_app_and_unsupported_chat_app_are_blocked() -> None:
    gate = ActionGate(POLICY)
    unknown = CommandIntent(CommandKind.OPEN_APP, "unknown-program")
    other_chat = CommandIntent(CommandKind.OPEN_CHAT, "Ali", "whatsapp")

    assert gate.observe(CommandResolution(0, unknown)) == ActionNotice(
        ActionKey(0, 0), unknown, ActionNoticeReason.NOT_ALLOWED
    )
    assert gate.observe(CommandResolution(1, other_chat)) == ActionNotice(
        ActionKey(0, 1), other_chat, ActionNoticeReason.NOT_ALLOWED
    )
    assert gate.verified_context == VerifiedContext()


def test_confirmation_requires_explicit_approval() -> None:
    policy = ActionPolicy(
        allowed_chat_apps=frozenset({"telegram"}),
        confirmation_required_for=frozenset({CommandKind.OPEN_CHAT}),
    )
    gate = ActionGate(policy)
    first = ActionKey(0, 0)
    second = ActionKey(0, 1)

    assert gate.observe(CommandResolution(0, ALI_CHAT)) == ActionNotice(
        first, ALI_CHAT, ActionNoticeReason.CONFIRMATION_REQUIRED
    )
    assert gate.verified_context == VerifiedContext()
    assert gate.confirm(first, approved=False) == ActionNotice(
        first, ALI_CHAT, ActionNoticeReason.CANCELLED
    )
    with pytest.raises(ValueError, match="confirmation"):
        gate.confirm(first, approved=True)

    assert gate.observe(CommandResolution(1, ALI_CHAT)) == ActionNotice(
        second, ALI_CHAT, ActionNoticeReason.CONFIRMATION_REQUIRED
    )
    assert gate.confirm(second, approved=True) == ActionRequest(second, ALI_CHAT)
    assert gate.verified_context == VerifiedContext()


def test_failure_reports_voice_and_text_without_changing_context() -> None:
    gate = ActionGate(POLICY)
    key = ActionKey(0, 0)
    assert gate.observe(CommandResolution(0, TELEGRAM)) == ActionRequest(key, TELEGRAM)
    gate.record_result(ActionResult(key, ActionOutcome.CONFIRMED, "telegram"))
    browser_key = ActionKey(0, 1)
    assert gate.observe(CommandResolution(1, BROWSER)) == ActionRequest(
        browser_key, BROWSER
    )
    assert gate.record_result(
        ActionResult(browser_key, ActionOutcome.FAILED, error_code="not_found")
    ) == (
        ActionFeedback(
            browser_key,
            BROWSER,
            ActionOutcome.FAILED,
            ResponseChannel.TEXT_AND_VOICE,
            "not_found",
        )
    )
    assert gate.verified_context == VerifiedContext(active_app="telegram")


def test_reported_success_without_observed_app_does_not_invent_context() -> None:
    gate = ActionGate(POLICY)
    key = ActionKey(0, 0)
    gate.observe(CommandResolution(0, TELEGRAM))
    gate.record_result(ActionResult(key, ActionOutcome.CONFIRMED))
    assert gate.verified_context == VerifiedContext()


def test_unverified_or_unknown_launch_does_not_invent_context() -> None:
    gate = ActionGate(POLICY)
    accepted = ActionKey(0, 0)
    unknown = ActionKey(0, 1)
    gate.observe(CommandResolution(0, TELEGRAM))
    assert gate.record_result(
        ActionResult(accepted, ActionOutcome.LAUNCH_ACCEPTED)
    ) == ActionFeedback(
        accepted, TELEGRAM, ActionOutcome.LAUNCH_ACCEPTED, ResponseChannel.TEXT_ONLY
    )
    assert gate.verified_context == VerifiedContext()

    gate.observe(CommandResolution(1, BROWSER))
    assert gate.record_result(
        ActionResult(unknown, ActionOutcome.UNKNOWN, error_code="launcher_timeout")
    ) == ActionFeedback(
        unknown,
        BROWSER,
        ActionOutcome.UNKNOWN,
        ResponseChannel.TEXT_AND_VOICE,
        "launcher_timeout",
    )
    assert gate.verified_context == VerifiedContext()


def test_unverified_new_app_invalidates_previous_verified_app() -> None:
    gate = ActionGate(POLICY)
    gate.observe(CommandResolution(0, TELEGRAM))
    gate.record_result(
        ActionResult(ActionKey(0, 0), ActionOutcome.CONFIRMED, "telegram")
    )
    assert gate.verified_context == VerifiedContext(active_app="telegram")

    gate.observe(CommandResolution(1, BROWSER))
    gate.record_result(ActionResult(ActionKey(0, 1), ActionOutcome.LAUNCH_ACCEPTED))
    assert gate.verified_context == VerifiedContext()


def test_pending_capacity_fails_explicitly_and_recovers_after_result() -> None:
    gate = ActionGate(ActionPolicy(allowed_apps=frozenset({"telegram"}), max_pending=1))
    first = ActionKey(0, 0)
    assert gate.observe(CommandResolution(0, TELEGRAM)) == ActionRequest(
        first, TELEGRAM
    )
    assert gate.observe(CommandResolution(1, TELEGRAM)) == ActionNotice(
        ActionKey(0, 1), TELEGRAM, ActionNoticeReason.BUSY
    )
    gate.record_result(ActionResult(first, ActionOutcome.CONFIRMED, "telegram"))
    assert gate.observe(CommandResolution(2, TELEGRAM)) == ActionRequest(
        ActionKey(0, 2), TELEGRAM
    )


def test_fresh_app_observation_can_inform_the_next_command() -> None:
    coordinator = CommandCoordinator(DemoCommandInterpreter())
    gate = ActionGate(POLICY)
    first = coordinator.observe(
        TranscriptUpdate(0, "تلگرام را باز کن", TranscriptStatus.FINAL, "fa")
    )
    assert gate.observe(first[0]) == ActionRequest(ActionKey(0, 0), TELEGRAM, "fa")
    assert gate.verified_context == VerifiedContext()

    gate.record_result(
        ActionResult(ActionKey(0, 0), ActionOutcome.CONFIRMED, "telegram")
    )
    assert gate.verified_context == VerifiedContext(active_app="telegram")
    second = coordinator.observe(
        TranscriptUpdate(1, "چت علی را باز کن", TranscriptStatus.FINAL, "fa"),
        observed_active_app="telegram",  # A separate fresh OS observation.
    )
    assert gate.observe(second[0]) == ActionRequest(ActionKey(0, 1), ALI_CHAT, "fa")


def test_policy_and_results_reject_invalid_metadata() -> None:
    with pytest.raises(ValueError, match="max_pending"):
        ActionPolicy(max_pending=0)
    with pytest.raises(ValueError, match="identifiers"):
        ActionPolicy(allowed_apps=frozenset({" "}))
    with pytest.raises(ValueError, match="IDs"):
        ActionKey(-1, 0)
    with pytest.raises(ValueError, match="only confirmed"):
        ActionResult(ActionKey(0, 0), ActionOutcome.FAILED, "telegram")
    with pytest.raises(ValueError, match="error_code"):
        ActionResult(ActionKey(0, 0), ActionOutcome.FAILED, error_code=" ")
    with pytest.raises(ValueError, match="cannot report"):
        ActionResult(ActionKey(0, 0), ActionOutcome.CONFIRMED, error_code="not_found")
    with pytest.raises(ValueError, match="require an error_code"):
        ActionResult(ActionKey(0, 0), ActionOutcome.UNKNOWN)


def test_new_stream_can_reuse_segment_id_without_dedup_collision() -> None:
    gate = ActionGate(POLICY)
    first = ActionKey(0, 0)
    second = ActionKey(1, 0)
    assert gate.observe(CommandResolution(0, TELEGRAM)) == ActionRequest(
        first, TELEGRAM
    )
    gate.record_result(ActionResult(first, ActionOutcome.CONFIRMED, "telegram"))
    assert gate.observe(CommandResolution(0, BROWSER, stream_id=1)) == ActionRequest(
        second, BROWSER
    )


def test_out_of_order_results_keep_the_language_of_each_command() -> None:
    gate = ActionGate(POLICY)
    first = ActionKey(0, 0)
    second = ActionKey(0, 1)
    assert gate.observe(CommandResolution(0, TELEGRAM, language="en")) == (
        ActionRequest(first, TELEGRAM, "en")
    )
    assert gate.observe(CommandResolution(1, BROWSER, language="fa")) == (
        ActionRequest(second, BROWSER, "fa")
    )
    second_feedback = gate.record_result(
        ActionResult(second, ActionOutcome.FAILED, error_code="not_found")
    )
    first_feedback = gate.record_result(
        ActionResult(first, ActionOutcome.LAUNCH_ACCEPTED)
    )
    assert second_feedback.language == "fa"
    assert first_feedback.language == "en"


def test_confirmation_retains_original_command_language() -> None:
    gate = ActionGate(
        ActionPolicy(
            allowed_chat_apps=frozenset({"telegram"}),
            confirmation_required_for=frozenset({CommandKind.OPEN_CHAT}),
        )
    )
    key = ActionKey(0, 0)
    notice = gate.observe(CommandResolution(0, ALI_CHAT, language="fa"))
    assert isinstance(notice, ActionNotice)
    assert notice.language == "fa"
    assert gate.confirm(key, approved=True) == ActionRequest(key, ALI_CHAT, "fa")
