"""Resolved model targets must still be spoken in the original utterance."""

import pytest

from kyrin.commands.models import CommandContext
from kyrin.commands.operation_verifier import (
    OperationVerificationStatus,
    SourceOperationVerifier,
)
from kyrin.commands.target_grounding import SourceTargetGrounder, TargetGroundingStatus
from kyrin.commands.target_resolution import SemanticTargetResolver
from kyrin.commands.understanding import (
    MeaningStep,
    ProposedMeaning,
    RequestedOperation,
    UnderstandingInput,
    UnderstandingResult,
    UnderstandingStatus,
)
from kyrin.desktop.app_catalog import InstalledApp
from kyrin.desktop.spoken_app_names import CatalogSpokenAppResolver


class Catalog:
    def list_apps(self) -> tuple[InstalledApp, ...]:
        return (
            InstalledApp("telegram.desktop", "Telegram"),
            InstalledApp("browser.desktop", "Browser"),
            InstalledApp("whatsapp.desktop", "WhatsApp"),
        )

    def find_app(self, platform_id: str) -> InstalledApp | None:
        return next(
            (app for app in self.list_apps() if app.platform_id == platform_id), None
        )


def names() -> CatalogSpokenAppResolver:
    return CatalogSpokenAppResolver(
        Catalog(),
        {
            "telegram.desktop": "telegram",
            "browser.desktop": "browser",
            "whatsapp.desktop": "whatsapp",
        },
        {
            "telegram": ("تلگرام", "تلیگرام"),
            "browser": ("مرورگر",),
            "whatsapp": ("واتساپ",),
        },
    )


def check(
    text: str,
    language: str,
    *steps: MeaningStep,
    active_app: str | None = None,
    alternatives: tuple[str, ...] = (),
) -> tuple[TargetGroundingStatus, str | None]:
    proposal = UnderstandingResult(UnderstandingStatus.READY, (ProposedMeaning(steps),))
    source = UnderstandingInput(text, language, alternatives)
    assert (
        SourceOperationVerifier().verify(source, proposal).status
        is OperationVerificationStatus.MATCHED
    )
    app_names = names()
    resolution = SemanticTargetResolver(
        app_names,
        allowed_apps=("telegram", "browser", "whatsapp"),
        supported_chat_apps=("telegram", "whatsapp"),
    ).resolve(proposal, context=CommandContext(observed_active_app=active_app))
    outcome = SourceTargetGrounder(app_names).verify(source, proposal, resolution)
    return outcome.status, outcome.reason


@pytest.mark.parametrize(
    ("text", "language", "target", "operation"),
    [
        ("Open Telegram", "en", "Telegram", RequestedOperation.OPEN_APP),
        ("Open the browser", "en", "Browser", RequestedOperation.OPEN_APP),
        (
            "Close Telegram window",
            "en",
            "Telegram",
            RequestedOperation.CLOSE_APP_WINDOW,
        ),
        ("تلگرام را باز کن", "fa", "Telegram", RequestedOperation.OPEN_APP),
        ("تلیگرام را باز کن", "fa", "Telegram", RequestedOperation.OPEN_APP),
        ("مرورگر رو باز کن", "fa", "Browser", RequestedOperation.OPEN_APP),
    ],
)
def test_exact_source_app_identity_matches(
    text: str, language: str, target: str, operation: RequestedOperation
) -> None:
    status, reason = check(text, language, MeaningStep(operation, target))
    assert (status, reason) == (TargetGroundingStatus.MATCHED, None)


@pytest.mark.parametrize(
    ("text", "language"),
    [("Open Telegram", "en"), ("تلگرام را باز کن", "fa")],
)
def test_wrong_but_allowed_app_is_blocked(text: str, language: str) -> None:
    assert check(
        text, language, MeaningStep(RequestedOperation.OPEN_APP, "Browser")
    ) == (
        TargetGroundingStatus.CLARIFY,
        "app_mismatch",
    )


def test_fuzzy_source_name_does_not_authorize_exact_model_target() -> None:
    assert check(
        "Open Telegrum", "en", MeaningStep(RequestedOperation.OPEN_APP, "Telegram")
    ) == (TargetGroundingStatus.CLARIFY, "app_mismatch")


def test_chat_name_and_explicit_app_are_checked_separately() -> None:
    assert check(
        "Open Ali's chat in WhatsApp",
        "en",
        MeaningStep(RequestedOperation.OPEN_CHAT, "Ali", "WhatsApp"),
    ) == (TargetGroundingStatus.MATCHED, None)
    assert check(
        "Open Ali's chat in WhatsApp",
        "en",
        MeaningStep(RequestedOperation.OPEN_CHAT, "Alice", "WhatsApp"),
    ) == (TargetGroundingStatus.CLARIFY, "chat_name_mismatch")
    assert check(
        "Open Ali's chat in WhatsApp",
        "en",
        MeaningStep(RequestedOperation.OPEN_CHAT, "Ali", "Telegram"),
    ) == (TargetGroundingStatus.CLARIFY, "chat_app_mismatch")


def test_chat_context_cannot_be_invented_by_model() -> None:
    assert check(
        "Open Ali's chat",
        "en",
        MeaningStep(RequestedOperation.OPEN_CHAT, "Ali"),
        active_app="telegram",
    ) == (TargetGroundingStatus.MATCHED, None)
    assert check(
        "Open Ali's chat",
        "en",
        MeaningStep(RequestedOperation.OPEN_CHAT, "Ali", "WhatsApp"),
        active_app="telegram",
    ) == (TargetGroundingStatus.CLARIFY, "unspoken_chat_app")


def test_ordered_two_step_targets_and_alternative_transcripts() -> None:
    steps = (
        MeaningStep(RequestedOperation.OPEN_APP, "Telegram"),
        MeaningStep(RequestedOperation.OPEN_CHAT, "Ali"),
    )
    assert check("Open Telegram and open Ali's chat", "en", *steps) == (
        TargetGroundingStatus.MATCHED,
        None,
    )
    assert check(
        "Open Telegram and open Ali's chat",
        "en",
        *steps,
        alternatives=("Open browser and open Ali's chat",),
    ) == (TargetGroundingStatus.CLARIFY, "alternative_target_conflict")


def test_persian_chat_name_and_app() -> None:
    assert check(
        "چت علی را در واتساپ باز کن",
        "fa",
        MeaningStep(RequestedOperation.OPEN_CHAT, "علی", "WhatsApp"),
    ) == (TargetGroundingStatus.MATCHED, None)
