"""Independent role evidence, real alternatives and unchanged execution boundaries."""

from dataclasses import replace

import pytest

from kyrin.commands.app_names import SpokenAppCandidate
from kyrin.commands.interpreter import (
    NeedsClarification,
    NotACommand,
    ReadyCommand,
    ReadyPlan,
    UnrecognizedCommand,
)
from kyrin.commands.model_interpreter import ModelAssistedInterpreter
from kyrin.commands.models import (
    CommandContext,
    CommandIntent,
    CommandKind,
    PendingOperationClarification,
    PendingWindowSelection,
)
from kyrin.commands.recovery_candidates import (
    RECOVERY_CONTRACTS,
    PhoneticCandidateGenerator,
)
from kyrin.commands.speech_recovery import (
    SpeechCommandRecovery,
    SpeechRecoveryInterpreter,
)
from kyrin.commands.understanding import (
    ConfirmationDecision,
    MeaningStep,
    ProposedMeaning,
    RequestedOperation,
    UnderstandingInput,
    UnderstandingResult,
    UnderstandingStatus,
)
from kyrin.stt.evidence import SpeechEvidence, SpeechHypothesis
from scripts.commands.evaluate_l04_baseline import fixture


def phonemes(text: str) -> str:
    return {
        "oh pen": "open",
        "cloze": "close",
        "screwl": "scroll",
        "serch": "search",
        "openz": "open",
        "nue window": "new window",
        "nue tab": "new tab",
        "prefrences": "preferences",
        "doun": "down",
        "ap": "up",
        "enabel": "enable",
        "disabel": "disable",
    }.get(text, text)


def generator() -> PhoneticCandidateGenerator:
    names, _ = fixture()
    return PhoneticCandidateGenerator(
        names,
        allowed_apps=frozenset({"telegram", "browser", "school", "terminal"}),
        chat_apps=frozenset({"telegram"}),
        phonemize=phonemes,
    )


def test_every_kind_requires_an_explicit_contract() -> None:
    assert len(RECOVERY_CONTRACTS) == len(CommandKind)
    assert {c.kind for c in RECOVERY_CONTRACTS} == set(CommandKind)
    assert all(c.roles and c.requirement for c in RECOVERY_CONTRACTS)


@pytest.mark.parametrize(
    "text",
    [
        "Type school down",
        "The school is down the road.",
        'Say "scroll down"',
        "Do not cloze Telegram",
        "screwl up down",
        "Powerz off this computer",
        "Stop listning",
    ],
)
def test_no_global_replacement_or_unknown_destination(text: str) -> None:
    assert not generator().generate(
        text, "en", CommandContext(observed_active_app="telegram")
    )


@pytest.mark.parametrize(
    ("text", "kind", "target"),
    [
        ("oh pen Telegram", CommandKind.OPEN_APP, "telegram"),
        ("cloze Telegram", CommandKind.CLOSE_APP_WINDOW, "telegram"),
        ("screwl down", CommandKind.SCROLL_DOWN, "telegram"),
        (
            "serch for Do not open Telegram",
            CommandKind.TELEGRAM_SEARCH,
            "Do not open Telegram",
        ),
        ("openz chat Alice in Telegram", CommandKind.OPEN_CHAT, "Alice"),
        ("openz Telegram archive", CommandKind.TELEGRAM_VIEW, "archive"),
    ],
)
def test_roles_produce_native_intents_without_rewriting_source(
    text: str, kind: CommandKind, target: str
) -> None:
    candidates = generator().generate(
        text, "en", CommandContext(observed_active_app="telegram")
    )
    assert candidates[0].intent.kind is kind and candidates[0].intent.target == target
    assert candidates[0].original_text == text


def test_pending_menu_and_window_number_keep_their_scope() -> None:
    menu = PendingOperationClarification(
        SpokenAppCandidate("terminal", "Terminal"),
        (CommandKind.NEW_APP_WINDOW, CommandKind.NEW_APP_TAB),
    )
    result = generator().generate("nue window", "en", CommandContext(), menu)
    assert result[0].intent == CommandIntent(CommandKind.NEW_APP_WINDOW, "terminal")
    assert not generator().generate("nue window", "en", CommandContext())
    picker = PendingWindowSelection(
        SpokenAppCandidate("desktop", "Windows"), 3, all_apps=True
    )
    result = generator().generate("cloze number 2", "en", CommandContext(), picker)
    assert result[0].intent.window_index == 2
    assert not generator().generate("cloze number 4", "en", CommandContext(), picker)


class Model:
    def __init__(self, operation: RequestedOperation) -> None:
        self.operation = operation
        self.sources: list[UnderstandingInput] = []

    def understand(
        self, utterance: UnderstandingInput, *, context: CommandContext
    ) -> UnderstandingResult:
        self.sources.append(utterance)
        return UnderstandingResult(
            UnderstandingStatus.READY,
            (ProposedMeaning((MeaningStep(self.operation, "Telegram"),)),),
        )

    def classify_confirmation(
        self, utterance: UnderstandingInput, *, question: str
    ) -> ConfirmationDecision:
        return ConfirmationDecision.UNCLEAR


def interpreter(model: Model) -> SpeechRecoveryInterpreter:
    names, rules = fixture()
    recovery = SpeechCommandRecovery(generator(), rules)
    base = ModelAssistedInterpreter(
        rules,
        model,
        names,
        allowed_apps=frozenset({"telegram", "browser", "school"}),
        supported_chat_apps=frozenset({"telegram"}),
        action_review=rules.review_model_action,
        recovery_review=recovery.review,
    )
    return SpeechRecoveryInterpreter(base, recovery)


def test_semantic_proposal_must_agree_with_original_phonetic_evidence() -> None:
    model = Model(RequestedOperation.OPEN_APP)
    context = CommandContext(observed_active_app="telegram")
    result = interpreter(model).interpret(
        "oh pen Telegram", language="en", context=context, pending=None
    )
    assert isinstance(result, ReadyCommand)
    assert result.intent.recovery is not None
    assert result.intent.recovery.original_text == "oh pen Telegram"
    assert model.sources[0].text == "oh pen Telegram"
    wrong = interpreter(Model(RequestedOperation.OPEN_APP)).interpret(
        "cloze Telegram", language="en", context=context, pending=None
    )
    assert isinstance(wrong, UnrecognizedCommand)


def test_real_alternative_conflict_blocks_even_the_fast_path() -> None:
    model = Model(RequestedOperation.OPEN_APP)
    context = CommandContext(
        speech_evidence=SpeechEvidence(
            "vosk", (SpeechHypothesis("Close Telegram", "vosk"),)
        )
    )
    result = interpreter(model).interpret(
        "Open Telegram", language="en", context=context, pending=None
    )
    assert isinstance(result, NeedsClarification)
    assert model.sources == []
    context = replace(
        context,
        speech_evidence=SpeechEvidence(
            "vosk", (SpeechHypothesis("open Telegram", "vosk"),)
        ),
    )
    assert isinstance(
        interpreter(model).interpret(
            "Open Telegram", language="en", context=context, pending=None
        ),
        ReadyCommand,
    )


def test_partial_never_uses_model_or_phonetic_recovery() -> None:
    model = Model(RequestedOperation.OPEN_APP)
    result = interpreter(model).interpret(
        "oh pen Telegram",
        language="en",
        context=CommandContext(is_final_transcript=False),
        pending=None,
    )
    assert not isinstance(result, ReadyCommand)
    assert model.sources == []


def test_reprocessing_preserves_original_and_releases_pcm_before_model() -> None:
    from kyrin.stt.audio_recovery import AudioRecoveryPolicy, RetainedAudio

    owner = RetainedAudio(
        b"\x01\x00" * 8,
        lambda pcm: SpeechHypothesis(
            "Open Telegram", "whisper.cpp", "same_audio_reprocess"
        ),
        AudioRecoveryPolicy(),
    )

    class InspectModel(Model):
        def understand(
            self, utterance: UnderstandingInput, *, context: CommandContext
        ) -> UnderstandingResult:
            assert owner.retained_bytes == 0
            assert utterance.text == "oh pen Telegram"
            assert utterance.evidence is not None
            assert utterance.evidence.alternatives[0].origin == "same_audio_reprocess"
            return super().understand(utterance, context=context)

    model = InspectModel(RequestedOperation.OPEN_APP)
    result = interpreter(model).interpret(
        "oh pen Telegram",
        language="en",
        pending=None,
        context=CommandContext(retained_audio=owner),
    )
    assert isinstance(result, ReadyCommand)
    assert owner.attempts == 1


def test_phonetic_app_identity_requires_a_targeted_question() -> None:
    model = Model(RequestedOperation.OPEN_APP)
    result = interpreter(model).interpret(
        "oh pen Telegrum",
        language="en",
        context=CommandContext(),
        pending=None,
    )
    assert isinstance(result, NeedsClarification)
    from kyrin.commands.models import PendingAppClarification

    assert isinstance(result.pending, PendingAppClarification)
    assert result.pending.confirmation
    assert result.pending.candidates[0].app_id == "telegram"


@pytest.mark.parametrize(
    ("spoken", "kind"),
    [
        ("screwl doun", CommandKind.SCROLL_DOWN),
        ("screwl ap", CommandKind.SCROLL_UP),
    ],
)
def test_direction_is_independently_grounded(spoken: str, kind: CommandKind) -> None:
    context = CommandContext(observed_scroll_app="telegram")
    candidates = generator().generate(spoken, "en", context)
    assert candidates[0].intent.kind is kind
    recovery = SpeechCommandRecovery(generator(), fixture()[1])
    proposal = UnderstandingResult(
        UnderstandingStatus.READY,
        (ProposedMeaning((MeaningStep(RequestedOperation(kind.value)),)),),
    )
    assert isinstance(
        recovery.review(UnderstandingInput(spoken, "en"), proposal, context),
        ReadyCommand,
    )
    opposite = (
        RequestedOperation.SCROLL_UP
        if kind is CommandKind.SCROLL_DOWN
        else RequestedOperation.SCROLL_DOWN
    )
    wrong = replace(proposal, candidates=(ProposedMeaning((MeaningStep(opposite),)),))
    assert isinstance(
        recovery.review(UnderstandingInput(spoken, "en"), wrong, context),
        UnrecognizedCommand,
    )
    assert not generator().generate("screwl sideways", "en", context)
    assert not generator().generate("screwl up doun", "en", context)


def test_payload_is_never_phonemized_or_split_as_a_plan() -> None:
    seen: list[str] = []

    def record(text: str) -> str:
        seen.append(text)
        return phonemes(text)

    names, _ = fixture()
    retrieval = PhoneticCandidateGenerator(
        names,
        allowed_apps=frozenset({"telegram"}),
        chat_apps=frozenset({"telegram"}),
        phonemize=record,
    )
    text = "serch for Alice and Bob in Telegram"
    result = retrieval.generate(
        text, "en", CommandContext(observed_active_app="telegram")
    )
    assert result[0].intent.target == "Alice and Bob in Telegram"
    assert result[0].following == ()
    assert not any(
        "alice" in item.casefold() or "bob" in item.casefold() for item in seen
    )


@pytest.mark.parametrize("text", ["Do not cloze Telegram", "Type school down"])
def test_explicit_non_actions_do_not_request_repetition(text: str) -> None:
    model = Model(RequestedOperation.OPEN_APP)
    result = interpreter(model).interpret(
        text, language="en", context=CommandContext(), pending=None
    )
    assert isinstance(result, NotACommand)
    assert not model.sources


def test_multistep_requires_every_ordered_step_and_preserves_review() -> None:
    class PlanModel(Model):
        first_target = "Telegram"

        def understand(
            self, utterance: UnderstandingInput, *, context: CommandContext
        ) -> UnderstandingResult:
            self.sources.append(utterance)
            return UnderstandingResult(
                UnderstandingStatus.READY,
                (
                    ProposedMeaning(
                        (
                            MeaningStep(RequestedOperation.OPEN_APP, self.first_target),
                            MeaningStep(RequestedOperation.MINIMIZE_APP, "Browser"),
                        )
                    ),
                ),
            )

    model = PlanModel(RequestedOperation.OPEN_APP)
    text = "oh pen Telegram then minimize Browser"
    result = interpreter(model).interpret(
        text, language="en", context=CommandContext(), pending=None
    )
    assert isinstance(result, ReadyPlan)
    assert [(step.kind, step.target) for step in result.plan.steps] == [
        (CommandKind.OPEN_APP, "telegram"),
        (CommandKind.MINIMIZE_APP, "browser"),
    ]
    assert all(
        step.recovery is not None and step.recovery.original_text == text
        for step in result.plan.steps
    )
    wrong = interpreter(Model(RequestedOperation.OPEN_APP)).interpret(
        text, language="en", context=CommandContext(), pending=None
    )
    assert isinstance(wrong, UnrecognizedCommand)
    terminal_model = PlanModel(RequestedOperation.OPEN_APP)
    terminal_model.first_target = "Terminal"
    terminal = interpreter(terminal_model).interpret(
        "oh pen Terminal then minimize Browser",
        language="en",
        context=CommandContext(),
        pending=None,
    )
    assert not isinstance(terminal, ReadyPlan)
    assert not generator().generate(
        "oh pen Telegram then delete files", "en", CommandContext()
    )
    assert not generator().generate(
        "oh pen Telegram then minimize it", "en", CommandContext()
    )
    assert not generator().generate(
        "oh pen Telegram and open Browser and close School and minimize Browser",
        "en",
        CommandContext(),
    )


def test_queue_wait_consumes_budget_and_releases_audio() -> None:
    from time import monotonic_ns

    from kyrin.stt.audio_recovery import AudioRecoveryPolicy, RetainedAudio

    owner = RetainedAudio(b"\x00\x00", lambda pcm: None, AudioRecoveryPolicy())
    model = Model(RequestedOperation.OPEN_APP)
    result = interpreter(model).interpret(
        "oh pen Telegram",
        language="en",
        pending=None,
        context=CommandContext(
            transcript_emitted_ns=monotonic_ns() - 121_000_000_000, retained_audio=owner
        ),
    )
    assert isinstance(result, UnrecognizedCommand)
    assert not model.sources and owner.retained_bytes == 0


def test_complete_non_action_never_reprocesses_retained_audio() -> None:
    from kyrin.stt.audio_recovery import AudioRecoveryPolicy, RetainedAudio

    calls: list[bytes] = []

    def retry(pcm: bytes) -> None:
        calls.append(pcm)

    owner = RetainedAudio(b"\x00\x00", retry, AudioRecoveryPolicy())
    result = interpreter(Model(RequestedOperation.OPEN_APP)).interpret(
        "Do not open Telegram",
        language="en",
        pending=None,
        context=CommandContext(retained_audio=owner),
    )
    assert isinstance(result, NotACommand)
    assert not calls and owner.retained_bytes == 0


@pytest.mark.parametrize("state", [True, False])
def test_visible_state_recovery_through_production_composition(state: bool) -> None:
    from time import monotonic

    from kyrin.commands.visible_options import VisibleOption
    from kyrin.desktop.window_observation import WindowObservation

    class Reader:
        def read_options(
            self, expected_app: str, utterance: str
        ) -> tuple[VisibleOption, ...]:
            now = monotonic()
            observation = WindowObservation(
                expected_app, 1, "test-window", "test-generation", now, now + 2
            )
            return (
                VisibleOption(
                    "1",
                    "Notifications",
                    "accessibility",
                    checked=not state,
                    observation=observation,
                ),
            )

    class StateModel(Model):
        def understand(
            self, utterance: UnderstandingInput, *, context: CommandContext
        ) -> UnderstandingResult:
            self.sources.append(utterance)
            return UnderstandingResult(
                UnderstandingStatus.READY,
                (
                    ProposedMeaning(
                        (
                            MeaningStep(
                                RequestedOperation.VISIBLE_CONTROL,
                                "Notifications",
                                control_state=state,
                            ),
                        )
                    ),
                ),
            )

    names, rules = fixture()
    recovery = SpeechCommandRecovery(generator(), rules)
    model = StateModel(RequestedOperation.VISIBLE_CONTROL)
    base = ModelAssistedInterpreter(
        rules,
        model,
        names,
        allowed_apps=frozenset({"telegram"}),
        supported_chat_apps=frozenset({"telegram"}),
        allow_visible_control=True,
        visible_options_reader=Reader(),
        action_review=rules.review_model_action,
        recovery_review=recovery.review,
    )
    text = ("enabel" if state else "disabel") + " Notifications"
    result = SpeechRecoveryInterpreter(base, recovery).interpret(
        text,
        language="en",
        pending=None,
        context=CommandContext(observed_scroll_app="telegram"),
    )
    assert isinstance(result, ReadyCommand)
    assert result.intent.kind is CommandKind.VISIBLE_CONTROL
    assert result.intent.control_state is state
    assert result.intent.control_observation is not None
    assert result.intent.recovery is not None
    assert [item.text for item in model.sources] == [text]


@pytest.mark.parametrize(
    ("text", "state"),
    [("enabel Notifications", True), ("disabel Notifications", False)],
)
def test_visible_state_requires_current_evidence_and_semantic_state(
    text: str, state: bool
) -> None:
    from time import monotonic

    from kyrin.commands.visible_options import VisibleOption
    from kyrin.desktop.window_observation import WindowObservation

    now = monotonic()
    observation = WindowObservation("telegram", 1, "window", "generation", now, now + 2)
    option = VisibleOption(
        "1", "Notifications", "accessibility", checked=False, observation=observation
    )
    context = CommandContext(
        observed_scroll_app="telegram",
        visible_control_enabled=True,
        visible_options=(option,),
    )
    recovery = SpeechCommandRecovery(generator(), fixture()[1])
    proposal = UnderstandingResult(
        UnderstandingStatus.READY,
        (
            ProposedMeaning(
                (
                    MeaningStep(
                        RequestedOperation.VISIBLE_CONTROL,
                        "Notifications",
                        control_state=state,
                        target_id="1",
                    ),
                )
            ),
        ),
    )
    source = UnderstandingInput(text, "en")
    result = recovery.review(source, proposal, context)
    assert isinstance(result, ReadyCommand) and result.intent.control_state is state
    wrong = replace(
        proposal,
        candidates=(
            ProposedMeaning(
                (replace(proposal.candidates[0].steps[0], control_state=not state),)
            ),
        ),
    )
    assert isinstance(recovery.review(source, wrong, context), UnrecognizedCommand)
    assert not generator().generate(
        text, "en", replace(context, visible_options=(replace(option, checked=None),))
    )
    expired = replace(observation, observed_at=now - 5, deadline=now - 3)
    assert not generator().generate(
        text,
        "en",
        replace(context, visible_options=(replace(option, observation=expired),)),
    )
