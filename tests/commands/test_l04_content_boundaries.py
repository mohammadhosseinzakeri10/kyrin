"""Reported words and unsupported search payloads cannot seed action consent."""

import pytest

from kyrin.commands.coordinator import CommandCoordinator
from kyrin.commands.model_interpreter import ModelAssistedInterpreter
from kyrin.commands.models import (
    CommandContext,
    CommandResolution,
    ResponseKind,
    ResponseRequest,
)
from kyrin.commands.understanding import (
    ConfirmationDecision,
    MeaningStep,
    ProposedMeaning,
    RequestedOperation,
    UncertaintyKind,
    UnderstandingInput,
    UnderstandingResult,
    UnderstandingStatus,
)
from kyrin.stt.transcript import TranscriptStatus, TranscriptUpdate
from scripts.commands.evaluate_l04_baseline import fixture


class ActionInsideContent:
    calls = 0

    def understand(
        self, source: UnderstandingInput, *, context: CommandContext
    ) -> UnderstandingResult:
        self.calls += 1
        return UnderstandingResult(
            UnderstandingStatus.READY,
            (
                ProposedMeaning(
                    (MeaningStep(RequestedOperation.MINIMIZE_APP, "Telegram"),)
                ),
            ),
        )

    def classify_confirmation(
        self, source: UnderstandingInput, *, question: str
    ) -> ConfirmationDecision:
        return ConfirmationDecision.YES


@pytest.mark.parametrize(
    "text",
    [
        'The words "Minimize Telegram" are on the screen.',
        'The phrase "Minimize Telegram" is an example.',
        'It says "Minimize Telegram".',
        'This says "Minimize Telegram".',
        'I said "Minimize Telegram" yesterday.',
        "Search the web for Minimize Telegram",
        '"Minimize Telegram"',
    ],
)
def test_content_cannot_start_confirmation_or_request_repetition(text: str) -> None:
    names, rules = fixture()
    model = ActionInsideContent()
    interpreter = ModelAssistedInterpreter(
        rules,
        model,
        names,
        allowed_apps=frozenset({"telegram"}),
        supported_chat_apps=frozenset({"telegram"}),
        action_review=rules.review_model_action,
    )
    coordinator = CommandCoordinator(interpreter)
    events = coordinator.observe(
        TranscriptUpdate(0, text, TranscriptStatus.FINAL, "en")
    )
    assert not any(isinstance(e, CommandResolution) and e.intent for e in events)
    assert not any(
        isinstance(e, ResponseRequest)
        and e.kind in {ResponseKind.CONFIRM_ACTION, ResponseKind.REPEAT_COMMAND}
        for e in events
    )
    assert coordinator.pending_clarification is None
    assert model.calls == 0


def test_search_payload_and_chat_name_are_kept_on_supported_paths() -> None:
    names, rules = fixture()
    model = ActionInsideContent()
    interpreter = ModelAssistedInterpreter(
        rules,
        model,
        names,
        allowed_apps=frozenset({"telegram"}),
        supported_chat_apps=frozenset({"telegram"}),
    )
    coordinator = CommandCoordinator(interpreter)
    events = coordinator.observe(
        TranscriptUpdate(
            0, "Search for Do not open Telegram", TranscriptStatus.FINAL, "en"
        ),
        observed_active_app="telegram",
    )
    intent = next(
        e.intent for e in events if isinstance(e, CommandResolution) and e.intent
    )
    assert intent.target == "Do not open Telegram"
    assert intent.kind.value == "telegram_search"
    assert model.calls == 0


@pytest.mark.parametrize(
    "text", ["How do I minimize Telegram?", "What does minimize Telegram mean?"]
)
@pytest.mark.parametrize(
    "status", [UnderstandingStatus.READY, UnderstandingStatus.AMBIGUOUS]
)
def test_informational_question_rejects_model_action_without_seeding_consent(
    text: str, status: UnderstandingStatus,
) -> None:
    names, rules = fixture()
    class QuestionModel(ActionInsideContent):
        def understand(
            self, source: UnderstandingInput, *, context: CommandContext
        ) -> UnderstandingResult:
            if status is UnderstandingStatus.READY:
                return super().understand(source, context=context)
            self.calls += 1
            return UnderstandingResult(
                status, uncertainties=frozenset({UncertaintyKind.OPERATION})
            )

    model = QuestionModel()
    interpreter = ModelAssistedInterpreter(
        rules,
        model,
        names,
        allowed_apps=frozenset({"telegram"}),
        supported_chat_apps=frozenset({"telegram"}),
    )
    coordinator = CommandCoordinator(interpreter)
    events = coordinator.observe(
        TranscriptUpdate(0, text, TranscriptStatus.FINAL, "en")
    )
    assert not any(isinstance(e, CommandResolution) and e.intent for e in events)
    assert not any(isinstance(e, ResponseRequest) for e in events)
    assert coordinator.pending_clarification is None
    assert model.calls == 1


def test_informational_question_preserves_conversational_reply() -> None:
    from kyrin.commands.interpreter import ConversationalReply

    class ReplyModel(ActionInsideContent):
        def understand(
            self, source: UnderstandingInput, *, context: CommandContext
        ) -> UnderstandingResult:
            self.calls += 1
            return UnderstandingResult(
                UnderstandingStatus.RESPOND, reply="KYRIN is a desktop assistant."
            )

    names, rules = fixture()
    model = ReplyModel()
    interpreter = ModelAssistedInterpreter(
        rules,
        model,
        names,
        allowed_apps=frozenset({"telegram"}),
        supported_chat_apps=frozenset({"telegram"}),
    )
    result = interpreter.interpret(
        "What is KYRIN?", language="en", context=CommandContext(), pending=None
    )
    assert result == ConversationalReply("KYRIN is a desktop assistant.")
    assert model.calls == 1


@pytest.mark.parametrize(
    "text",
    [
        'Could you say "Minimize Telegram"?',
        "Would you please type Minimize Telegram?",
        'Can you quote "Minimize Telegram"?',
    ],
)
def test_polite_content_role_cannot_seed_model_action(text: str) -> None:
    names, rules = fixture()
    model = ActionInsideContent()
    interpreter = ModelAssistedInterpreter(
        rules,
        model,
        names,
        allowed_apps=frozenset({"telegram"}),
        supported_chat_apps=frozenset({"telegram"}),
    )
    events = CommandCoordinator(interpreter).observe(
        TranscriptUpdate(0, text, TranscriptStatus.FINAL, "en")
    )
    assert not any(isinstance(e, ResponseRequest) for e in events)
    assert not any(isinstance(e, CommandResolution) and e.intent for e in events)
    assert model.calls == 0


@pytest.mark.parametrize(
    "text",
    [
        "Send this to Test Contact",
        "Please delete Test Document",
        "Could you pay Test Vendor",
    ],
)
def test_unsupported_payload_operation_does_not_prompt_for_repetition(
    text: str,
) -> None:
    names, rules = fixture()
    model = ActionInsideContent()
    interpreter = ModelAssistedInterpreter(
        rules,
        model,
        names,
        allowed_apps=frozenset({"telegram"}),
        supported_chat_apps=frozenset({"telegram"}),
    )
    events = CommandCoordinator(interpreter).observe(
        TranscriptUpdate(0, text, TranscriptStatus.FINAL, "en")
    )
    assert not any(isinstance(e, ResponseRequest) for e in events)
    assert not any(isinstance(e, CommandResolution) and e.intent for e in events)
    assert model.calls == 0


@pytest.mark.parametrize(
    "negative", ["Do not select any option", "Don't create a new tab"]
)
def test_negative_menu_answer_clears_dialogue_before_new_command(negative: str) -> None:
    _, rules = fixture(1)
    coordinator = CommandCoordinator(rules)
    coordinator.observe(
        TranscriptUpdate(0, "Open Terminal", TranscriptStatus.FINAL, "en")
    )
    assert coordinator.pending_clarification is not None
    declined = coordinator.observe(
        TranscriptUpdate(1, negative, TranscriptStatus.FINAL, "en")
    )
    assert not any(isinstance(e, ResponseRequest) for e in declined)
    assert coordinator.pending_clarification is None
    fresh = coordinator.observe(
        TranscriptUpdate(2, "Open Browser", TranscriptStatus.FINAL, "en")
    )
    assert any(
        isinstance(e, CommandResolution) and e.intent and e.intent.target == "browser"
        for e in fresh
    )
