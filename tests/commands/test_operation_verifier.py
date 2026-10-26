"""The independent source-text operation check fails closed on uncertainty."""

import pytest

from kyrin.commands.operation_verifier import (
    OperationVerificationStatus,
    SourceOperationVerifier,
)
from kyrin.commands.understanding import (
    MeaningStep,
    ProposedMeaning,
    RequestedOperation,
    UnderstandingInput,
    UnderstandingResult,
    UnderstandingStatus,
)


def proposed(*operations: RequestedOperation) -> UnderstandingResult:
    return UnderstandingResult(
        UnderstandingStatus.READY,
        (
            ProposedMeaning(
                tuple(MeaningStep(operation, "target") for operation in operations)
            ),
        ),
    )


@pytest.mark.parametrize(
    ("text", "language", "operations"),
    [
        ("Open Telegram.", "en", (RequestedOperation.OPEN_APP,)),
        ("Gently open Telegram.", "en", (RequestedOperation.OPEN_APP,)),
        ("Kairin, please close Telegram", "en", (RequestedOperation.CLOSE_APP_WINDOW,)),
        ("Exit Telegram", "en", (RequestedOperation.CLOSE_APP_WINDOW,)),
        ("Quit Telegram", "en", (RequestedOperation.CLOSE_APP_WINDOW,)),
        ("Kyrene, please open Telegram", "en", (RequestedOperation.OPEN_APP,)),
        ("Minimize Telegram", "en", (RequestedOperation.MINIMIZE_APP,)),
        ("Hide Telegram", "en", (RequestedOperation.MINIMIZE_APP,)),
        ("Launch Telegram", "en", (RequestedOperation.OPEN_APP,)),
        ("Switch to Telegram", "en", (RequestedOperation.OPEN_APP,)),
        (
            "Open Telegram and open Ali's chat",
            "en",
            (RequestedOperation.OPEN_APP, RequestedOperation.OPEN_CHAT),
        ),
        ("تلگرام را باز کن", "fa", (RequestedOperation.OPEN_APP,)),
        ("تلگرام را اجرا کن", "fa", (RequestedOperation.OPEN_APP,)),
        ("تلگرام را پنهان کن", "fa", (RequestedOperation.MINIMIZE_APP,)),
        ("تلیگرام را باز کن", "fa", (RequestedOperation.OPEN_APP,)),
        ("چت علی را باز کن", "fa", (RequestedOperation.OPEN_CHAT,)),
        (
            "تلگرام را باز کن و چت علی را باز کن",
            "fa",
            (RequestedOperation.OPEN_APP, RequestedOperation.OPEN_CHAT),
        ),
        ("تلگرام را ببند", "fa", (RequestedOperation.CLOSE_APP_WINDOW,)),
    ],
)
def test_explicit_supported_operations_match(
    text: str, language: str, operations: tuple[RequestedOperation, ...]
) -> None:
    result = SourceOperationVerifier().verify(
        UnderstandingInput(text, language), proposed(*operations)
    )
    assert result.status is OperationVerificationStatus.MATCHED


@pytest.mark.parametrize(
    ("text", "language", "operation"),
    [
        ("Restart Telegram", "en", RequestedOperation.OPEN_APP),
        ("تلگرام را دوباره راه‌اندازی کن", "fa", RequestedOperation.OPEN_APP),
        ("Do not open Telegram", "en", RequestedOperation.OPEN_APP),
        ("تلگرام را باز نکن", "fa", RequestedOperation.OPEN_APP),
        ("تلگرام رو باز نکنم", "fa", RequestedOperation.OPEN_APP),
        ("Open browser and search for a book", "en", RequestedOperation.OPEN_APP),
        ("Open Telegram or browser", "en", RequestedOperation.OPEN_APP),
        ("I think open Telegram is good", "en", RequestedOperation.OPEN_APP),
        ("Öffne Telegram", "de", RequestedOperation.OPEN_APP),
    ],
)
def test_unsafe_or_uncovered_source_requires_clarification(
    text: str, language: str, operation: RequestedOperation
) -> None:
    result = SourceOperationVerifier().verify(
        UnderstandingInput(text, language), proposed(operation)
    )
    assert result.status is OperationVerificationStatus.CLARIFY


def test_proposed_operation_must_match_source_and_order() -> None:
    verifier = SourceOperationVerifier()
    assert (
        verifier.verify(
            UnderstandingInput("Close Telegram", "en"),
            proposed(RequestedOperation.OPEN_APP),
        ).reason
        == "operation_mismatch"
    )
    assert (
        verifier.verify(
            UnderstandingInput("Open Telegram and close browser", "en"),
            proposed(RequestedOperation.CLOSE_APP_WINDOW, RequestedOperation.OPEN_APP),
        ).reason
        == "operation_mismatch"
    )


def test_alternative_transcript_conflict_blocks_a_proposal() -> None:
    result = SourceOperationVerifier().verify(
        UnderstandingInput("Open Telegram", "en", ("Close Telegram",)),
        proposed(RequestedOperation.OPEN_APP),
    )
    assert result.status is OperationVerificationStatus.CLARIFY
    assert result.reason == "alternative_transcript_conflict"


def test_negative_and_system_proposals_cannot_match_application_operations() -> None:
    verifier = SourceOperationVerifier()
    negative = UnderstandingResult(UnderstandingStatus.NOT_COMMAND)
    assert (
        verifier.verify(UnderstandingInput("Anything", "en"), negative).status
        is OperationVerificationStatus.NO_ACTION
    )
    system = UnderstandingResult(
        UnderstandingStatus.READY,
        (ProposedMeaning((MeaningStep(RequestedOperation.RESTART_SYSTEM),)),),
    )
    assert (
        verifier.verify(
            UnderstandingInput("Restart this computer", "en"), system
        ).status
        is OperationVerificationStatus.UNSUPPORTED
    )
