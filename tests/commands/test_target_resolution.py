"""Proposed model targets cannot bypass catalog or context checks."""

from kyrin.commands.app_names import SpokenAppCandidate, SpokenAppMatch
from kyrin.commands.models import CommandContext
from kyrin.commands.target_resolution import (
    SemanticTargetResolver,
    TargetResolutionStatus,
)
from kyrin.commands.understanding import (
    MeaningStep,
    Polarity,
    ProposedMeaning,
    RequestedOperation,
    UncertaintyKind,
    UnderstandingResult,
    UnderstandingStatus,
)


class StubAppNames:
    def resolve(self, spoken_name: str) -> SpokenAppMatch:
        names = {
            "Telegram": SpokenAppMatch(
                (SpokenAppCandidate("telegram", "Telegram"),), True
            ),
            "WhatsApp": SpokenAppMatch(
                (SpokenAppCandidate("whatsapp", "WhatsApp"),), True
            ),
            "Telegrum": SpokenAppMatch((SpokenAppCandidate("telegram", "Telegram"),)),
            "Shared": SpokenAppMatch(
                (
                    SpokenAppCandidate("telegram", "Telegram"),
                    SpokenAppCandidate("whatsapp", "WhatsApp"),
                ),
                True,
            ),
        }
        return names.get(spoken_name, SpokenAppMatch())

    def suggest(self, spoken_name: str) -> SpokenAppMatch:
        return self.resolve(spoken_name)


def resolver(
    *, allowed: tuple[str, ...] = ("telegram", "whatsapp")
) -> SemanticTargetResolver:
    return SemanticTargetResolver(
        StubAppNames(),
        allowed_apps=allowed,
        supported_chat_apps=("telegram", "whatsapp"),
    )


def ready(*steps: MeaningStep) -> UnderstandingResult:
    return UnderstandingResult(UnderstandingStatus.READY, (ProposedMeaning(steps),))


def test_exact_allowed_app_resolves_only_to_proposal() -> None:
    resolution = resolver().resolve(
        ready(MeaningStep(RequestedOperation.OPEN_APP, "Telegram")),
        context=CommandContext(),
    )
    assert resolution.status is TargetResolutionStatus.RESOLVED
    assert resolution.steps[0].app_id == "telegram"
    assert resolution.steps[0].target_phrase is None


def test_fuzzy_unknown_duplicate_and_unallowed_names_cannot_resolve() -> None:
    for phrase in ("Telegrum", "Unknown", "Shared", "WhatsApp"):
        resolution = resolver(allowed=("telegram",)).resolve(
            ready(MeaningStep(RequestedOperation.OPEN_APP, phrase)),
            context=CommandContext(),
        )
        expected = (
            TargetResolutionStatus.RESOLVED
            if phrase == "Shared"
            else TargetResolutionStatus.CLARIFY
        )
        assert resolution.status is expected
    # An exact name shared by two allowed applications also needs clarification.
    shared = resolver().resolve(
        ready(MeaningStep(RequestedOperation.OPEN_APP, "Shared")),
        context=CommandContext(),
    )
    assert shared.status is TargetResolutionStatus.CLARIFY
    assert shared.candidates == ("telegram", "whatsapp")


def test_chat_without_app_requires_fresh_unconflicted_foreground() -> None:
    proposal = ready(MeaningStep(RequestedOperation.OPEN_CHAT, "Ali"))
    assert (
        resolver()
        .resolve(proposal, context=CommandContext(last_referenced_app="telegram"))
        .status
        is TargetResolutionStatus.CLARIFY
    )
    conflict = resolver().resolve(
        proposal,
        context=CommandContext("telegram", "whatsapp"),
    )
    assert conflict.status is TargetResolutionStatus.CLARIFY
    assert conflict.candidates == ("telegram", "whatsapp")
    resolved = resolver().resolve(
        proposal, context=CommandContext(observed_active_app="whatsapp")
    )
    assert resolved.status is TargetResolutionStatus.RESOLVED
    assert resolved.steps[0].app_id == "whatsapp"
    assert resolved.steps[0].target_phrase == "Ali"


def test_explicit_chat_app_must_be_allowed_and_chat_capable() -> None:
    proposal = ready(MeaningStep(RequestedOperation.OPEN_CHAT, "Ali", "WhatsApp"))
    assert (
        resolver(allowed=("telegram",))
        .resolve(proposal, context=CommandContext())
        .status
        is TargetResolutionStatus.CLARIFY
    )


def test_no_partial_plan_if_later_target_is_unclear() -> None:
    proposal = ready(
        MeaningStep(RequestedOperation.OPEN_APP, "Telegram"),
        MeaningStep(RequestedOperation.OPEN_APP, "Telegrum"),
    )
    resolution = resolver().resolve(proposal, context=CommandContext())
    assert resolution.status is TargetResolutionStatus.CLARIFY
    assert resolution.steps == ()


def test_implicit_chat_uses_prior_planned_app_but_does_not_execute_it() -> None:
    proposal = ready(
        MeaningStep(RequestedOperation.OPEN_APP, "Telegram"),
        MeaningStep(RequestedOperation.OPEN_CHAT, "Ali"),
    )
    resolution = resolver().resolve(
        proposal, context=CommandContext(observed_active_app="whatsapp")
    )
    assert resolution.status is TargetResolutionStatus.RESOLVED
    assert [step.app_id for step in resolution.steps] == ["telegram", "telegram"]
    assert resolution.steps[1].target_phrase == "Ali"


def test_negative_ambiguous_and_system_proposals_never_resolve() -> None:
    negative = UnderstandingResult(
        UnderstandingStatus.NEGATED,
        (
            ProposedMeaning(
                (
                    MeaningStep(
                        RequestedOperation.OPEN_APP,
                        "Telegram",
                        polarity=Polarity.NEGATED,
                    ),
                )
            ),
        ),
    )
    assert (
        resolver().resolve(negative, context=CommandContext()).status
        is TargetResolutionStatus.NO_ACTION
    )
    ambiguous = UnderstandingResult(
        UnderstandingStatus.AMBIGUOUS,
        uncertainties=frozenset({UncertaintyKind.TARGET}),
    )
    assert (
        resolver().resolve(ambiguous, context=CommandContext()).status
        is TargetResolutionStatus.CLARIFY
    )
    system = ready(MeaningStep(RequestedOperation.RESTART_SYSTEM))
    outcome = resolver().resolve(system, context=CommandContext())
    assert outcome.status is TargetResolutionStatus.UNSUPPORTED
    assert outcome.reason == "system_power_requires_separate_flow"
