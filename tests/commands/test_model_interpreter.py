"""A command model may propose, but original speech and policy still decide."""

import json
from pathlib import Path

import pytest

from kyrin.actions.gate import ActionGate, ActionPolicy
from kyrin.actions.models import ActionOutcome, ActionRequest, ActionResult
from kyrin.commands.app_names import ModelAppOption, SpokenAppCandidate
from kyrin.commands.coordinator import CommandCoordinator
from kyrin.commands.demo_interpreter import DemoCommandInterpreter
from kyrin.commands.interpreter import (
    ConversationalReply,
    Interpretation,
    NeedsClarification,
    NotACommand,
    ReadyCommand,
    UnrecognizedCommand,
)
from kyrin.commands.model_interpreter import ModelAssistedInterpreter
from kyrin.commands.models import (
    CommandCandidateUpdate,
    CommandContext,
    CommandIntent,
    CommandKind,
    CommandResolution,
    PendingAppClarification,
    PendingOperationClarification,
    ResponseChannel,
    ResponseKind,
    ResponseRequest,
)
from kyrin.commands.ollama_engine import CommandModelError, OllamaCommandEngine
from kyrin.commands.understanding import (
    ConfirmationDecision,
    MeaningStep,
    ProposedMeaning,
    RequestedOperation,
    UnderstandingInput,
    UnderstandingResult,
    UnderstandingStatus,
)
from kyrin.commands.visible_options import VisibleOption
from kyrin.desktop.accessibility_target import AccessibilityTarget
from kyrin.desktop.platforms.xdg import XdgDesktopAppCatalog
from kyrin.desktop.spoken_app_names import CatalogSpokenAppResolver
from kyrin.desktop.window_presence import WindowPresence
from kyrin.model_resources import MemorySnapshot, ModelResources
from kyrin.responses.presenter import ResponsePresenter
from kyrin.runtime.command_runtime import dispatch_command_action
from kyrin.stt.device import DevicePreference
from kyrin.stt.transcript import TranscriptStatus, TranscriptUpdate


class FakeModel:
    def __init__(
        self,
        result: UnderstandingResult | Exception,
        confirmation: ConfirmationDecision | Exception = ConfirmationDecision.UNCLEAR,
    ) -> None:
        self.result = result
        self.confirmation = confirmation
        self.calls = 0
        self.confirmation_calls = 0
        self.last_context: CommandContext | None = None

    def understand(
        self, source: UnderstandingInput, *, context: CommandContext
    ) -> UnderstandingResult:
        self.calls += 1
        self.last_context = context
        if isinstance(self.result, Exception):
            raise self.result
        return self.result

    def classify_confirmation(
        self, source: UnderstandingInput, *, question: str
    ) -> ConfirmationDecision:
        self.confirmation_calls += 1
        if isinstance(self.confirmation, Exception):
            raise self.confirmation
        return self.confirmation


def _ready(operation: RequestedOperation, target: str) -> UnderstandingResult:
    return UnderstandingResult(
        UnderstandingStatus.READY,
        (ProposedMeaning((MeaningStep(operation, target),)),),
    )


def _interpreter(
    tmp_path: Path,
    model: FakeModel,
    *,
    supported_chat_apps: frozenset[str] = frozenset(),
    visible_options: tuple[VisibleOption, ...] = (),
    allow_visible_control: bool = False,
    available_operations: tuple[str, ...] | None = None,
) -> ModelAssistedInterpreter:
    applications = tmp_path / "applications"
    applications.mkdir(exist_ok=True)
    (applications / "telegram.desktop").write_text(
        "[Desktop Entry]\nType=Application\nName=Telegram\n", encoding="utf-8"
    )
    (applications / "browser.desktop").write_text(
        "[Desktop Entry]\nType=Application\nName=Browser\n", encoding="utf-8"
    )
    (applications / "code.desktop").write_text(
        "[Desktop Entry]\nType=Application\nName=Visual Studio Code\n",
        encoding="utf-8",
    )
    names = CatalogSpokenAppResolver(
        XdgDesktopAppCatalog((tmp_path,)),
        {
            "telegram.desktop": "telegram",
            "browser.desktop": "browser",
            "code.desktop": "visual-studio-code",
        },
        {"telegram": ("تلگرام", "تيليغرام", "ٹیلیگرام")},
    )
    rules = DemoCommandInterpreter(names)
    return ModelAssistedInterpreter(
        rules,
        model,
        names,
        allowed_apps=frozenset({"telegram", "browser", "visual-studio-code"}),
        supported_chat_apps=supported_chat_apps,
        allow_visible_control=allow_visible_control,
        visible_options_reader=(
            FakeVisibleOptionsReader(visible_options) if allow_visible_control else None
        ),
        available_operations=available_operations,
        action_review=rules.review_model_action,
    )


class FakeVisibleOptionsReader:
    def __init__(self, options: tuple[VisibleOption, ...]) -> None:
        self.options = options

    def read_options(
        self, expected_app: str, utterance: str
    ) -> tuple[VisibleOption, ...]:
        assert expected_app == "example.desktop"
        assert utterance
        return self.options


def _visible_ready(
    spoken_target: str, option_id: str | None, state: bool | None = None
) -> UnderstandingResult:
    return UnderstandingResult(
        UnderstandingStatus.READY,
        (
            ProposedMeaning(
                (
                    MeaningStep(
                        RequestedOperation.VISIBLE_CONTROL,
                        spoken_target,
                        control_state=state,
                        target_id=option_id,
                    ),
                )
            ),
        ),
    )


def test_natural_request_does_not_correct_spelling_from_model_option_id(
    tmp_path: Path,
) -> None:
    model = FakeModel(_visible_ready("seating", "1"))
    option = VisibleOption("1", "Settings", "accessibility", "button", anchor=(75, 42))
    interpreter = _interpreter(
        tmp_path, model, visible_options=(option,), allow_visible_control=True
    )
    result = interpreter.interpret(
        "Could you open seating please?",
        language="en",
        context=CommandContext(observed_scroll_app="example.desktop"),
        pending=None,
    )

    assert isinstance(result, UnrecognizedCommand)
    assert model.last_context is not None
    assert model.last_context.visible_options == (option,)


@pytest.mark.parametrize("wrong_label", ("Help", "Quit"))
def test_visible_option_id_cannot_change_spoken_target(
    tmp_path: Path, wrong_label: str
) -> None:
    model = FakeModel(_visible_ready("Settings", "2"))
    interpreter = _interpreter(
        tmp_path,
        model,
        visible_options=(
            VisibleOption("1", "Settings", "accessibility"),
            VisibleOption("2", wrong_label, "accessibility"),
        ),
        allow_visible_control=True,
    )

    result = interpreter.interpret(
        "I want Settings opened",
        language="en",
        context=CommandContext(observed_scroll_app="example.desktop"),
        pending=None,
    )

    assert isinstance(result, UnrecognizedCommand)


def test_natural_state_request_requires_matching_screen_option_and_direction(
    tmp_path: Path,
) -> None:
    structure = AccessibilityTarget(
        ((0, "FRAME", "Main"), (1, "SWITCH", "Notifications"))
    )
    option = VisibleOption(
        "2", "Notifications", "accessibility", "switch", True, accessibility=structure
    )
    context = CommandContext(observed_scroll_app="example.desktop")
    model = FakeModel(_visible_ready("Notifications", "2", False))
    interpreter = _interpreter(
        tmp_path, model, visible_options=(option,), allow_visible_control=True
    )
    assert interpreter.interpret(
        "I want Notifications off", language="en", context=context, pending=None
    ) == ReadyCommand(
        CommandIntent(
            CommandKind.VISIBLE_CONTROL,
            "Notifications",
            control_state=False,
            control_source="accessibility",
            control_accessibility=structure,
            control_window_app="example.desktop",
        )
    )
    model.result = _visible_ready("Notifications", "2", True)
    assert isinstance(
        interpreter.interpret(
            "I want Notifications off", language="en", context=context, pending=None
        ),
        UnrecognizedCommand,
    )


def test_unlisted_language_does_not_authorize_visible_control(
    tmp_path: Path,
) -> None:
    option = VisibleOption("2", "Benachrichtigungen", "accessibility", "switch", True)
    model = FakeModel(_visible_ready("Benachrichtigungen", None, False))
    interpreter = _interpreter(
        tmp_path, model, visible_options=(option,), allow_visible_control=True
    )
    result = interpreter.interpret(
        "Benachrichtigungen ausschalten",
        language="de",
        context=CommandContext(observed_scroll_app="example.desktop"),
        pending=None,
    )
    assert isinstance(result, UnrecognizedCommand)
    assert model.calls == 1
    assert model.last_context is not None
    assert model.last_context.visible_options == ()
    assert {item.app_id for item in model.last_context.available_apps} == {
        "telegram",
        "browser",
        "visual-studio-code",
    }


def test_multilingual_discovery_rejects_changed_model_target(tmp_path: Path) -> None:
    class ChangingModel(FakeModel):
        def understand(
            self, source: UnderstandingInput, *, context: CommandContext
        ) -> UnderstandingResult:
            self.calls += 1
            return _visible_ready(
                "Notifications" if context.visible_options else "Search",
                "1" if context.visible_options else None,
            )

    model = ChangingModel(_visible_ready("Search", None))
    interpreter = _interpreter(
        tmp_path,
        model,
        visible_options=(VisibleOption("1", "Zoeken", "accessibility"),),
        allow_visible_control=True,
    )
    result = interpreter.interpret(
        "Search openen",
        language="nl",
        context=CommandContext(observed_scroll_app="example.desktop"),
        pending=None,
    )
    assert isinstance(result, UnrecognizedCommand)
    assert model.calls == 2


def test_unlisted_language_scroll_requires_independent_source_rules(
    tmp_path: Path,
) -> None:
    model = FakeModel(
        UnderstandingResult(
            UnderstandingStatus.READY,
            (ProposedMeaning((MeaningStep(RequestedOperation.SCROLL_DOWN),)),),
        )
    )
    interpreter = _interpreter(tmp_path, model)
    assert isinstance(
        interpreter.interpret(
            "Weiter nach unten",
            language="de",
            context=CommandContext(observed_scroll_app="example.desktop"),
            pending=None,
        ),
        UnrecognizedCommand,
    )
    assert isinstance(
        interpreter.interpret(
            "Weiter nach unten",
            language="de",
            context=CommandContext(),
            pending=None,
        ),
        UnrecognizedCommand,
    )
    blocked = _interpreter(tmp_path, model, available_operations=("open_app",))
    assert isinstance(
        blocked.interpret(
            "Weiter nach unten",
            language="de",
            context=CommandContext(observed_scroll_app="example.desktop"),
            pending=None,
        ),
        UnrecognizedCommand,
    )


@pytest.mark.parametrize(
    "utterance",
    (
        "Please do not scroll down",
        'The words "scroll down" are on screen',
        "What is the weather today?",
    ),
)
def test_model_scroll_requires_explicit_affirmative_request(
    tmp_path: Path, utterance: str
) -> None:
    model = FakeModel(
        UnderstandingResult(
            UnderstandingStatus.READY,
            (ProposedMeaning((MeaningStep(RequestedOperation.SCROLL_DOWN),)),),
        )
    )
    interpreter = _interpreter(tmp_path, model)
    assert isinstance(
        interpreter.interpret(
            utterance,
            language="en",
            context=CommandContext(observed_scroll_app="example.desktop"),
            pending=None,
        ),
        NotACommand
        if utterance == "Please do not scroll down"
        else UnrecognizedCommand,
    )


@pytest.mark.parametrize(
    ("text", "language", "source_operation"),
    (
        ("Could you scroll up on this page please", "en", "scroll_up"),
        ("Would you scroll down in the current window please?", "en-US", "scroll_down"),
        ("لطفا این صفحه را به بالا اسکرول کن", "fa", "scroll_up"),
        ("لطفا این صفحه را به پایین اسکرول کن", "fa-IR", "scroll_down"),
        ("Could you scroll up or down on this page please", "en", None),
        ("Could you scroll down and then up please", "en", None),
        ("Could you scroll on this page please", "en", None),
        ("Could you scroll down please, do not do it yet", "en", None),
        ("Could you scroll down if the page is ready", "en", None),
        ('Could you scroll down to the words "up here"', "en", None),
        ("Could you scroll down to 'up here'", "en", None),
        ("Could you scroll down to ‘up here’", "en", None),
        ("لطفا این صفحه را به پایین اسکرول نکن", "fa", None),
        ("لطفا این صفحه را به بالا یا پایین اسکرول کن", "fa", None),
        ("عبارت «به پایین اسکرول کن» را بخوان", "fa", None),
        ("Weiter nach unten", "de", None),
        ("Could you scroll down on this page please", "de", None),
        ("Could you scroll down on this page please", None, None),
    ),
)
@pytest.mark.parametrize(
    "proposed_operation", (RequestedOperation.SCROLL_UP, RequestedOperation.SCROLL_DOWN)
)
def test_scroll_fallback_matches_independent_direction_with_real_action_review(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    text: str,
    language: str | None,
    source_operation: str | None,
    proposed_operation: RequestedOperation,
) -> None:
    reviewed: list[CommandIntent] = []
    original_review = DemoCommandInterpreter.review_model_action

    def review(
        self: DemoCommandInterpreter, intent: CommandIntent, context: CommandContext
    ) -> Interpretation:
        reviewed.append(intent)
        return original_review(self, intent, context)

    monkeypatch.setattr(DemoCommandInterpreter, "review_model_action", review)
    model = FakeModel(
        UnderstandingResult(
            UnderstandingStatus.READY,
            (ProposedMeaning((MeaningStep(proposed_operation),)),),
        )
    )
    interpreter = _interpreter(
        tmp_path, model, available_operations=("scroll_up", "scroll_down")
    )
    # Use the production review, with real rules and a freshly observed app.
    # Neither a direct command nor a fake rules stub may satisfy this test.
    context = CommandContext(observed_scroll_app="example.desktop")
    direct = interpreter._rules.interpret(
        text, language=language, context=context, pending=None
    )
    assert isinstance(direct, (NotACommand, UnrecognizedCommand))

    result = interpreter.interpret(
        text, language=language, context=context, pending=None
    )

    assert model.calls == 1
    if source_operation == proposed_operation.value:
        intent = CommandIntent(CommandKind(source_operation), "example.desktop")
        assert result == ReadyCommand(intent)
        assert reviewed == [intent]
    else:
        assert isinstance(result, UnrecognizedCommand)
        assert reviewed == []


@pytest.mark.parametrize(
    ("observed_app", "available_operations"),
    ((None, ("scroll_up", "scroll_down")), ("example.desktop", ("open_app",))),
)
def test_grounded_scroll_fallback_still_requires_focus_and_enabled_operation(
    tmp_path: Path,
    observed_app: str | None,
    available_operations: tuple[str, ...],
) -> None:
    model = FakeModel(
        UnderstandingResult(
            UnderstandingStatus.READY,
            (ProposedMeaning((MeaningStep(RequestedOperation.SCROLL_UP),)),),
        )
    )
    interpreter = _interpreter(
        tmp_path, model, available_operations=available_operations
    )
    text = "Could you scroll up on this page please"
    context = CommandContext(observed_scroll_app=observed_app)
    assert isinstance(
        interpreter._rules.interpret(
            text, language="en", context=context, pending=None
        ),
        NotACommand,
    )
    assert isinstance(
        interpreter.interpret(text, language="en", context=context, pending=None),
        UnrecognizedCommand,
    )
    assert model.calls == 1


@pytest.mark.parametrize(
    "utterance",
    (
        "Please do not click Search",
        'What does "click Search" mean?',
        "The words click Search are on screen",
    ),
)
def test_model_visible_control_requires_explicit_affirmative_request(
    tmp_path: Path, utterance: str
) -> None:
    interpreter = _interpreter(
        tmp_path,
        FakeModel(_visible_ready("Search", "1")),
        visible_options=(VisibleOption("1", "Search", "accessibility"),),
        allow_visible_control=True,
    )
    assert isinstance(
        interpreter.interpret(
            utterance,
            language="en",
            context=CommandContext(observed_scroll_app="example.desktop"),
            pending=None,
        ),
        NotACommand
        if utterance == "Please do not click Search"
        else UnrecognizedCommand,
    )


def test_model_power_proposal_cannot_start_confirmation(tmp_path: Path) -> None:
    model = FakeModel(
        UnderstandingResult(
            UnderstandingStatus.READY,
            (ProposedMeaning((MeaningStep(RequestedOperation.RESTART_SYSTEM),)),),
        )
    )
    interpreter = _interpreter(tmp_path, model)
    assert isinstance(
        interpreter.interpret(
            "Restart Telegram",
            language="en",
            context=CommandContext(),
            pending=None,
        ),
        UnrecognizedCommand,
    )


def test_model_cannot_invent_visible_option_or_use_it_without_focus(
    tmp_path: Path,
) -> None:
    model = FakeModel(_visible_ready("Search", "9"))
    interpreter = _interpreter(
        tmp_path,
        model,
        visible_options=(VisibleOption("1", "Search", "ocr"),),
        allow_visible_control=True,
    )
    assert isinstance(
        interpreter.interpret(
            "Please tap Search",
            language="en",
            context=CommandContext(observed_scroll_app="example.desktop"),
            pending=None,
        ),
        UnrecognizedCommand,
    )
    assert isinstance(
        interpreter.interpret(
            "Please tap Search", language="en", context=CommandContext(), pending=None
        ),
        UnrecognizedCommand,
    )


def test_click_on_is_not_mistaken_for_switch_on(tmp_path: Path) -> None:
    model = FakeModel(_visible_ready("Search", "1"))
    interpreter = _interpreter(
        tmp_path,
        model,
        visible_options=(VisibleOption("1", "Search", "accessibility"),),
        allow_visible_control=True,
    )
    assert interpreter.interpret(
        "Could you click on Search?",
        language="en",
        context=CommandContext(observed_scroll_app="example.desktop"),
        pending=None,
    ) == ReadyCommand(
        CommandIntent(
            CommandKind.VISIBLE_CONTROL,
            "Search",
            control_source="accessibility",
            control_window_app="example.desktop",
        )
    )


def _interpret(
    interpreter: ModelAssistedInterpreter, text: str, language: str = "en"
) -> Interpretation:
    return interpreter.interpret(
        text, language=language, context=CommandContext(), pending=None
    )


@pytest.mark.parametrize(
    "phrase",
    (
        "Could you open Telegram please?",
        "Can you please launch Telegram for me?",
    ),
)
def test_common_polite_app_request_keeps_fast_path(tmp_path: Path, phrase: str) -> None:
    model = FakeModel(CommandModelError("model should not run"))
    result = _interpret(_interpreter(tmp_path, model), phrase)
    assert result == ReadyCommand(CommandIntent(CommandKind.OPEN_APP, "telegram"))
    assert model.calls == 0


def test_model_chat_target_keeps_source_capitalization(tmp_path: Path) -> None:
    model = FakeModel(_ready(RequestedOperation.OPEN_CHAT, "my mother"))
    interpreter = _interpreter(
        tmp_path, model, supported_chat_apps=frozenset({"telegram"})
    )

    result = interpreter.interpret(
        "Open the chat My Mother",
        language="en",
        context=CommandContext(observed_active_app="telegram"),
        pending=None,
    )

    assert result == ReadyCommand(
        CommandIntent(CommandKind.OPEN_CHAT, "My Mother", "telegram")
    )
    assert model.calls == 1


@pytest.mark.parametrize("phrase", ("Kindly open Telegram", "Gently open Telegram"))
def test_model_handles_a_phrase_not_covered_by_fast_rules(
    tmp_path: Path, phrase: str
) -> None:
    model = FakeModel(_ready(RequestedOperation.OPEN_APP, "Telegram"))
    result = _interpret(_interpreter(tmp_path, model), phrase)
    assert isinstance(result, ReadyCommand)
    assert result.intent.kind is CommandKind.OPEN_APP
    assert result.intent.target == "telegram"
    assert model.calls == 1


def test_new_explicit_command_replaces_pending_app_question(tmp_path: Path) -> None:
    model = FakeModel(_ready(RequestedOperation.OPEN_APP, "Browser"))
    pending = PendingAppClarification(
        (SpokenAppCandidate("telegram", "Telegram"),), confirmation=True
    )
    result = _interpreter(tmp_path, model).interpret(
        "Kindly open Browser",
        language="en",
        context=CommandContext(),
        pending=pending,
    )
    assert result == ReadyCommand(CommandIntent(CommandKind.OPEN_APP, "browser"))
    assert model.calls == 1
    assert model.confirmation_calls == 0


def test_new_command_cannot_use_the_old_pending_app_as_its_target(
    tmp_path: Path,
) -> None:
    model = FakeModel(_ready(RequestedOperation.OPEN_APP, "Telegram"))
    pending = PendingAppClarification(
        (SpokenAppCandidate("telegram", "Telegram"),), confirmation=True
    )
    result = _interpreter(tmp_path, model).interpret(
        "Kindly open Browser",
        language="en",
        context=CommandContext(),
        pending=pending,
    )
    assert not isinstance(result, ReadyCommand)


def test_old_utterance_cannot_supply_a_new_action_target(tmp_path: Path) -> None:
    model = FakeModel(_ready(RequestedOperation.OPEN_APP, "Telegram"))
    interpreter = _interpreter(tmp_path, model)
    result = interpreter.interpret(
        "Please open it",
        language="en",
        context=CommandContext(recent_utterances=("Open Telegram",)),
        pending=None,
    )
    assert not isinstance(result, ReadyCommand)


@pytest.mark.parametrize("name", ("Visual Studio Code", "VS Code"))
def test_polite_request_uses_registered_full_or_short_app_name(
    tmp_path: Path, name: str
) -> None:
    model = FakeModel(_ready(RequestedOperation.OPEN_APP, name))
    result = _interpret(_interpreter(tmp_path, model), f"Please open {name}")
    assert result == ReadyCommand(
        CommandIntent(CommandKind.OPEN_APP, "visual-studio-code")
    )


@pytest.mark.parametrize(
    ("heard", "language"),
    [
        ("Please open.", "en"),
        ("في جوال أستديو كوتو", "ar"),
        ("هي جوال أستديو قوده", "ar"),
        ("Kötü kutusunu açın.", "tr"),
    ],
)
def test_unrecognizable_stt_cannot_invent_visual_studio_code(
    tmp_path: Path, heard: str, language: str
) -> None:
    model = FakeModel(_ready(RequestedOperation.OPEN_APP, "Visual Studio Code"))
    result = _interpret(_interpreter(tmp_path, model), heard, language)
    assert not isinstance(result, (ReadyCommand, NeedsClarification))


@pytest.mark.parametrize(
    ("source", "operation", "target", "language"),
    [
        (
            "Kindly open Telegram",
            RequestedOperation.OPEN_APP,
            "Browser",
            "en",
        ),
        ("Do not open Telegram", RequestedOperation.OPEN_APP, "Telegram", "en"),
        ("Öffne Telegram", RequestedOperation.OPEN_APP, "Telegram", "de"),
    ],
)
def test_wrong_or_uncovered_proposals_cannot_execute(
    tmp_path: Path,
    source: str,
    operation: RequestedOperation,
    target: str,
    language: str,
) -> None:
    model = FakeModel(_ready(operation, target))
    result = _interpret(_interpreter(tmp_path, model), source, language)
    assert not isinstance(result, ReadyCommand)


def test_existing_fast_command_does_not_wait_for_model(tmp_path: Path) -> None:
    model = FakeModel(CommandModelError("not responding"))
    result = _interpret(_interpreter(tmp_path, model), "Open Telegram")
    assert isinstance(result, ReadyCommand)
    assert model.calls == 0


@pytest.mark.parametrize(
    ("text", "confirmation_pending"),
    (
        ("Hello Kairin", False),
        ("certainly", True),
        ("Kindly open Telegram", True),
        ("Could you open seating please?", False),
        ("Settings bitte", False),
    ),
)
def test_partial_uses_only_rules_before_any_heavy_dependency(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    text: str,
    confirmation_pending: bool,
) -> None:
    reads = {"catalog": 0, "controls": 0, "ocr": 0}
    original_catalog = CatalogSpokenAppResolver.model_options

    def model_options(self: CatalogSpokenAppResolver) -> tuple[ModelAppOption, ...]:
        reads["catalog"] += 1
        return original_catalog(self)

    def read_options(
        self: FakeVisibleOptionsReader, expected_app: str, utterance: str
    ) -> tuple[VisibleOption, ...]:
        reads["controls"] += 1
        # Simulate the inventory's OCR fallback without touching the desktop.
        reads["ocr"] += 1
        return self.options

    monkeypatch.setattr(CatalogSpokenAppResolver, "model_options", model_options)
    monkeypatch.setattr(FakeVisibleOptionsReader, "read_options", read_options)
    model = FakeModel(
        _visible_ready("Settings", None), confirmation=ConfirmationDecision.YES
    )
    interpreter = _interpreter(tmp_path, model, allow_visible_control=True)
    context = CommandContext(
        is_final_transcript=False, observed_scroll_app="example.desktop"
    )
    pending = (
        PendingAppClarification(
            (SpokenAppCandidate("telegram", "Telegram"),), confirmation=True
        )
        if confirmation_pending
        else None
    )
    expected = interpreter._rules.interpret(
        text, language="en", context=context, pending=pending
    )

    result = interpreter.interpret(
        text, language="en", context=context, pending=pending
    )

    assert (model.calls, model.confirmation_calls, reads) == (
        0,
        0,
        {"catalog": 0, "controls": 0, "ocr": 0},
    )
    assert result == expected

    # The same dependencies remain reachable for final text; the guard must
    # not disable confirmations or either visible-control discovery route.
    final = interpreter.interpret(
        text,
        language="en",
        context=CommandContext(observed_scroll_app="example.desktop"),
        pending=pending,
    )
    if text == "certainly":
        assert model.confirmation_calls == 1
        assert final == ReadyCommand(CommandIntent(CommandKind.OPEN_APP, "telegram"))
    else:
        assert model.calls >= 1
    if text in {"Could you open seating please?", "Settings bitte"}:
        assert reads == {"catalog": 1, "controls": 1, "ocr": 1}


def test_model_assisted_partial_preview_never_executes_and_final_still_does(
    tmp_path: Path,
) -> None:
    model = FakeModel(_ready(RequestedOperation.OPEN_APP, "Telegram"))
    coordinator = CommandCoordinator(_interpreter(tmp_path, model))
    gate = ActionGate(ActionPolicy(allowed_apps=frozenset({"telegram"})))
    executed: list[ActionRequest] = []

    class Executor:
        def execute(self, request: ActionRequest) -> ActionResult:
            executed.append(request)
            return ActionResult(request.key, ActionOutcome.LAUNCH_ACCEPTED)

    executor = Executor()
    intent = CommandIntent(CommandKind.OPEN_APP, "telegram")
    for text, expected in (
        ("Open Telegram", (CommandCandidateUpdate(0, intent),)),
        ("Kindly open Telegram", (CommandCandidateUpdate(0, None),)),
    ):
        events = coordinator.observe(
            TranscriptUpdate(0, text, TranscriptStatus.PARTIAL, "en")
        )
        assert events == expected
        for event in events:
            assert dispatch_command_action(event, gate, executor) == ()
        assert executed == []
        assert model.calls == 0

    events = coordinator.observe(
        TranscriptUpdate(0, "Kindly open Telegram", TranscriptStatus.FINAL, "en")
    )
    assert events[0] == CommandResolution(0, intent, language="en")
    for final_event in events:
        dispatch_command_action(final_event, gate, executor)
    assert model.calls == 1
    assert len(executed) == 1
    assert executed[0].intent == intent


@pytest.mark.parametrize("phrase", ("Kindly close Telegram", "Gently close Telegram"))
def test_explicit_polite_close_does_not_depend_on_model(
    tmp_path: Path, phrase: str
) -> None:
    model = FakeModel(UnderstandingResult(UnderstandingStatus.NOT_COMMAND))
    result = _interpret(_interpreter(tmp_path, model), phrase)
    assert result == ReadyCommand(
        CommandIntent(CommandKind.CLOSE_APP_WINDOW, "telegram")
    )
    assert model.calls == 0


def test_negated_polite_close_never_executes(tmp_path: Path) -> None:
    model = FakeModel(_ready(RequestedOperation.CLOSE_APP_WINDOW, "Telegram"))
    result = _interpret(_interpreter(tmp_path, model), "Kindly do not close Telegram")
    assert not isinstance(result, ReadyCommand)


def test_model_failure_fails_closed(tmp_path: Path) -> None:
    model = FakeModel(CommandModelError("not responding"))
    result = _interpret(_interpreter(tmp_path, model), "Kindly open Telegram")
    assert isinstance(result, UnrecognizedCommand)


def test_explicit_command_repeats_when_model_claims_no_action(tmp_path: Path) -> None:
    model = FakeModel(UnderstandingResult(UnderstandingStatus.NOT_COMMAND))
    result = _interpret(_interpreter(tmp_path, model), "Kindly open Telegram")
    assert isinstance(result, UnrecognizedCommand)


def test_greeting_gets_model_reply_without_an_action(tmp_path: Path) -> None:
    model = FakeModel(
        UnderstandingResult(UnderstandingStatus.RESPOND, reply="Hello! I'm KYRIN.")
    )
    interpreter = _interpreter(tmp_path, model)
    assert _interpret(interpreter, "Hello Kairin") == ConversationalReply(
        "Hello! I'm KYRIN."
    )
    coordinator = CommandCoordinator(interpreter)
    events = coordinator.observe(
        TranscriptUpdate(0, "Hello Kairin", TranscriptStatus.FINAL, "en")
    )
    assert events[0] == CommandResolution(0, None, language="en")
    assert isinstance(events[1], ResponseRequest)
    assert events[1].kind is ResponseKind.CONVERSATION
    assert events[1].channel is ResponseChannel.TEXT_AND_VOICE
    assert events[1].message == "Hello! I'm KYRIN."


def test_model_reply_cannot_replace_a_recognizable_action(tmp_path: Path) -> None:
    model = FakeModel(UnderstandingResult(UnderstandingStatus.RESPOND, reply="Done!"))
    result = _interpret(_interpreter(tmp_path, model), "Kindly open Telegram")
    assert isinstance(result, UnrecognizedCommand)


@pytest.mark.parametrize("reply", ("ja", "Ja!", "nein", "یا"))
def test_pending_app_confirmation_keeps_language_and_safety(
    tmp_path: Path, reply: str
) -> None:
    model = FakeModel(CommandModelError("offline"))
    pending = PendingAppClarification(
        (SpokenAppCandidate("telegram", "Telegram"),), confirmation=True
    )
    result = _interpreter(tmp_path, model).interpret(
        reply, language="de", context=CommandContext(), pending=pending
    )
    if reply.casefold().startswith("ja"):
        assert result == ReadyCommand(CommandIntent(CommandKind.OPEN_APP, "telegram"))
    else:
        assert not isinstance(result, ReadyCommand)
    assert model.calls == 0
    assert model.confirmation_calls == 0


def test_unreviewed_language_app_action_names_the_operation_before_confirmation(
    tmp_path: Path,
) -> None:
    model = FakeModel(_ready(RequestedOperation.MINIMIZE_APP, "Telegram"))
    coordinator = CommandCoordinator(_interpreter(tmp_path, model))
    question = coordinator.observe(
        TranscriptUpdate(0, "Telegram minimieren", TranscriptStatus.FINAL, "de")
    )
    assert isinstance(question[1], ResponseRequest)
    assert question[1].kind is ResponseKind.CONFIRM_ACTION
    assert question[1].operation_candidates == (CommandKind.MINIMIZE_APP,)
    assert ResponsePresenter("en").present(question[1]).text == (
        "Do you want me to minimize Telegram? Yes or no?"
    )
    result = coordinator.observe(
        TranscriptUpdate(1, "Ja", TranscriptStatus.FINAL, "de")
    )
    assert result[0] == CommandResolution(
        1, CommandIntent(CommandKind.MINIMIZE_APP, "telegram"), language="de"
    )


def test_unreviewed_language_app_action_requires_exact_spoken_app(
    tmp_path: Path,
) -> None:
    model = FakeModel(_ready(RequestedOperation.MINIMIZE_APP, "Telegram"))
    result = _interpreter(tmp_path, model).interpret(
        "Bitte minimieren",
        language="de",
        context=CommandContext(),
        pending=None,
    )
    assert isinstance(result, UnrecognizedCommand)


def test_close_cloud_needs_one_explicit_confirmation(
    tmp_path: Path,
) -> None:
    applications = tmp_path / "applications"
    applications.mkdir()
    (applications / "claude.desktop").write_text(
        "[Desktop Entry]\nType=Application\nName=Claude\n", encoding="utf-8"
    )
    names = CatalogSpokenAppResolver(
        XdgDesktopAppCatalog((tmp_path,)), {"claude.desktop": "claude"}
    )
    rules = DemoCommandInterpreter(names, allowed_close_apps=frozenset({"claude"}))
    model = FakeModel(
        CommandModelError("offline"), confirmation=CommandModelError("offline")
    )
    coordinator = CommandCoordinator(
        ModelAssistedInterpreter(
            rules,
            model,
            names,
            allowed_apps=frozenset({"claude"}),
            supported_chat_apps=frozenset(),
        )
    )

    first = coordinator.observe(
        TranscriptUpdate(0, "Close.", TranscriptStatus.FINAL, "en")
    )
    assert first == (CommandResolution(0, None, language="en"),)
    name_question = coordinator.observe(
        TranscriptUpdate(1, "Cloud", TranscriptStatus.FINAL, "en")
    )
    assert isinstance(name_question[1], ResponseRequest)
    assert name_question[1].kind is ResponseKind.CONFIRM_ACTION
    assert name_question[1].channel is ResponseChannel.TEXT_ONLY
    assert ResponsePresenter("en").present(name_question[1]).text == (
        "Do you really want me to close Claude? Yes or no?"
    )

    confirmed = coordinator.observe(
        TranscriptUpdate(2, "Yes.", TranscriptStatus.FINAL, "en")
    )
    assert confirmed[0] == CommandResolution(
        2,
        CommandIntent(CommandKind.CLOSE_APP_WINDOW, "claude"),
        language="en",
    )
    assert coordinator.pending_clarification is None
    assert model.confirmation_calls == 0


def test_new_close_command_is_not_classified_as_yes_to_old_app_question(
    tmp_path: Path,
) -> None:
    model = FakeModel(
        CommandModelError("offline"), confirmation=ConfirmationDecision.YES
    )
    names = CatalogSpokenAppResolver(XdgDesktopAppCatalog((tmp_path,)), {})
    pending = PendingAppClarification(
        (SpokenAppCandidate("claude", "Claude"),),
        confirmation=True,
        operation=CommandKind.CLOSE_APP_WINDOW,
    )
    interpreter = ModelAssistedInterpreter(
        DemoCommandInterpreter(),
        model,
        names,
        allowed_apps=frozenset({"claude"}),
        supported_chat_apps=frozenset(),
    )
    result = interpreter.interpret(
        "Close the code", language="en", context=CommandContext(), pending=pending
    )
    assert isinstance(result, UnrecognizedCommand)
    assert model.confirmation_calls == 0


def test_model_confirmed_terminal_name_still_asks_for_the_operation(
    tmp_path: Path,
) -> None:
    applications = tmp_path / "applications"
    applications.mkdir()
    (applications / "org.gnome.Ptyxis.desktop").write_text(
        "[Desktop Entry]\nType=Application\nName=Terminal\n", encoding="utf-8"
    )
    names = CatalogSpokenAppResolver(
        XdgDesktopAppCatalog((tmp_path,)),
        {"org.gnome.Ptyxis.desktop": "terminal"},
    )

    class Presence:
        def observe(self, app_id: str) -> WindowPresence:
            return WindowPresence.OPEN

        def count(self, app_id: str) -> int:
            return 1

    rules = DemoCommandInterpreter(
        names, window_presence=Presence(), terminal_app_id="terminal"
    )
    interpreter = ModelAssistedInterpreter(
        rules,
        FakeModel(CommandModelError("offline"), ConfirmationDecision.YES),
        names,
        allowed_apps=frozenset({"terminal"}),
        supported_chat_apps=frozenset(),
        action_review=rules.review_model_action,
    )
    pending = PendingAppClarification(
        (SpokenAppCandidate("terminal", "Terminal"),), confirmation=True
    )
    result = interpreter.interpret(
        "oui", language="fr", context=CommandContext(), pending=pending
    )
    assert isinstance(result, NeedsClarification)
    assert isinstance(result.pending, PendingOperationClarification)


def test_model_proposed_terminal_open_uses_window_aware_menu(tmp_path: Path) -> None:
    applications = tmp_path / "applications"
    applications.mkdir()
    (applications / "org.gnome.Ptyxis.desktop").write_text(
        "[Desktop Entry]\nType=Application\nName=Terminal\n", encoding="utf-8"
    )
    names = CatalogSpokenAppResolver(
        XdgDesktopAppCatalog((tmp_path,)),
        {"org.gnome.Ptyxis.desktop": "terminal"},
    )

    class Presence:
        def observe(self, app_id: str) -> WindowPresence:
            return WindowPresence.OPEN

        def count(self, app_id: str) -> int:
            return 1

    rules = DemoCommandInterpreter(
        names, window_presence=Presence(), terminal_app_id="terminal"
    )
    model = FakeModel(_ready(RequestedOperation.OPEN_APP, "Terminal"))
    interpreter = ModelAssistedInterpreter(
        rules,
        model,
        names,
        allowed_apps=frozenset({"terminal"}),
        supported_chat_apps=frozenset(),
        action_review=rules.review_model_action,
    )
    result = _interpret(interpreter, "Please open Terminal")
    assert isinstance(result, NeedsClarification)
    assert isinstance(result.pending, PendingOperationClarification)


@pytest.mark.parametrize(
    ("source", "language", "reply", "decision", "action"),
    [
        ("Ouvrir Telegram", "fr", "oui", ConfirmationDecision.YES, True),
        ("Ouvrir Telegram", "en", "oui", ConfirmationDecision.YES, True),
        ("打开 Telegram", "zh", "是", ConfirmationDecision.YES, True),
        ("Ouvrir Telegram", "fr", "non", ConfirmationDecision.NO, False),
        ("打开 Telegram", "zh", "不要", ConfirmationDecision.YES, False),
    ],
)
def test_unreviewed_language_requires_a_second_explicit_confirmation(
    tmp_path: Path,
    source: str,
    language: str,
    reply: str,
    decision: ConfirmationDecision,
    action: bool,
) -> None:
    model = FakeModel(
        _ready(RequestedOperation.OPEN_APP, "Telegram"), confirmation=decision
    )
    interpreter = _interpreter(tmp_path, model)
    first = _interpret(interpreter, source, language)
    assert isinstance(first, NeedsClarification)
    assert isinstance(first.pending, PendingAppClarification)
    second = interpreter.interpret(
        reply, language=language, context=CommandContext(), pending=first.pending
    )
    if action:
        assert isinstance(second, ReadyCommand)
        assert second.intent == CommandIntent(CommandKind.OPEN_APP, "telegram")
    else:
        assert not isinstance(second, ReadyCommand)


def test_model_cannot_invent_a_target_in_an_unreviewed_language(
    tmp_path: Path,
) -> None:
    model = FakeModel(_ready(RequestedOperation.OPEN_APP, "Telegram"))
    result = _interpret(_interpreter(tmp_path, model), "Ouvrir Browser", "fr")
    assert isinstance(result, UnrecognizedCommand)


@pytest.mark.parametrize(
    ("source", "language"),
    [("N'ouvre pas Telegram", "fr"), ("不要打开 Telegram", "en")],
)
def test_negated_uncovered_language_cannot_become_an_app_suggestion(
    tmp_path: Path, source: str, language: str
) -> None:
    model = FakeModel(_ready(RequestedOperation.OPEN_APP, "Telegram"))
    result = _interpret(_interpreter(tmp_path, model), source, language)
    assert not isinstance(result, (ReadyCommand, NeedsClarification))


@pytest.mark.parametrize(
    ("source", "language", "expected"),
    [
        ("اوپن تلگرام", "fa", ReadyCommand),
        ("اپن ٹیلیگرام", "ur", ReadyCommand),
        ("أوبين تيليغرام", "ar", ReadyCommand),
        ("Opend telegram", "sv", NeedsClarification),
        ("و بنتلقرام", "ar", NotACommand),
    ],
)
def test_observed_mixed_script_stt_output(
    tmp_path: Path, source: str, language: str, expected: type
) -> None:
    model = FakeModel(CommandModelError("offline"))
    result = _interpret(_interpreter(tmp_path, model), source, language)
    assert isinstance(result, expected)
    assert model.calls == (1 if source == "و بنتلقرام" else 0)


def test_ollama_device_options_and_probe() -> None:
    requests: list[dict[str, object]] = []

    def transport(url: str, payload: dict[str, object], timeout: float) -> object:
        if url.endswith("/api/generate"):
            return {"done": True, "done_reason": "unload"}
        requests.append(payload)
        return {
            "prompt_eval_count": 1000,
            "message": {"content": '{"route":"no_action","steps":[]}'},
        }

    for device, expected in (
        (DevicePreference.CPU, 0),
        (DevicePreference.GPU, 999),
        (DevicePreference.AUTO, None),
    ):

        def probe(url: str, model: str, selected: DevicePreference = device) -> int:
            return 0 if selected is DevicePreference.CPU else 1024

        engine = OllamaCommandEngine(
            "http://127.0.0.1:11435",
            "qwen3.5:4b",
            device,
            resources=ModelResources(memory=lambda: MemorySnapshot()),
            token_counter=lambda payload: 1000,
            transport=transport,
            device_probe=probe,
        )
        assert (
            engine.understand(
                UnderstandingInput("hello", "en"), context=CommandContext()
            ).status
            is UnderstandingStatus.NOT_COMMAND
        )
        options = requests[-1]["options"]
        assert isinstance(options, dict)
        if expected is None:
            assert "num_gpu" not in options
        else:
            assert options["num_gpu"] == expected


def test_ollama_receives_current_screen_options_and_supported_actions() -> None:
    request: dict[str, object] = {}

    def transport(url: str, payload: dict[str, object], timeout: float) -> object:
        if url.endswith("/api/generate"):
            return {"done": True, "done_reason": "unload"}
        request.update(payload)
        return {
            "prompt_eval_count": 1000,
            "message": {
                "content": json.dumps(
                    {
                        "route": "execute",
                        "steps": [
                            {
                                "operation": "visible_control",
                                "target": "seating",
                                "target_id": "1",
                            }
                        ],
                    }
                )
            },
        }

    engine = OllamaCommandEngine(
        "http://127.0.0.1:11435",
        "qwen3.5:4b",
        DevicePreference.AUTO,
        resources=ModelResources(memory=lambda: MemorySnapshot()),
        token_counter=lambda payload: 1000,
        transport=transport,
    )
    result = engine.understand(
        UnderstandingInput("تلگرام را باز کن", "fa"),
        context=CommandContext(
            visible_options=(VisibleOption("1", "Settings", "accessibility"),),
            available_apps=(
                ModelAppOption(
                    "telegram",
                    "telegram.desktop",
                    "Telegram",
                    tuple(f"localized-{index}" for index in range(30)) + ("تلگرام",),
                ),
            ),
            available_operations=("visible_control",),
        ),
    )
    assert result.candidates[0].steps[0].target_id == "1"
    messages = request["messages"]
    assert isinstance(messages, list)
    user = json.loads(messages[1]["content"])
    assert user["context"]["visible_options"][0]["label"] == "Settings"
    assert user["context"]["available_visible_actions"] == ["click"]
    assert user["context"]["installed_apps"][0]["platform_id"] == "telegram.desktop"
    aliases = user["context"]["installed_apps"][0]["alternate_names"]
    assert len(aliases) == 12
    assert "تلگرام" in aliases
    assert user["context"]["available_operations"] == ["visible_control"]


def test_ollama_can_request_control_discovery_without_screen_options() -> None:
    sent: dict[str, object] = {}

    def transport(url: str, payload: dict[str, object], timeout: float) -> object:
        if url.endswith("/api/generate"):
            return {"done": True, "done_reason": "unload"}
        sent.update(payload)
        return {
            "prompt_eval_count": 1000,
            "message": {"content": '{"route":"no_action","steps":[]}'},
        }

    engine = OllamaCommandEngine(
        "http://127.0.0.1:11435",
        "qwen3.5:4b",
        DevicePreference.AUTO,
        resources=ModelResources(memory=lambda: MemorySnapshot()),
        token_counter=lambda payload: 1000,
        transport=transport,
    )
    engine.understand(
        UnderstandingInput("Benachrichtigungen ausschalten", "de"),
        context=CommandContext(visible_control_enabled=True),
    )
    messages = sent["messages"]
    assert isinstance(messages, list)
    user = json.loads(messages[1]["content"])
    assert user["context"]["available_visible_actions"] == ["discover"]


def test_explicit_gpu_without_gpu_memory_does_not_claim_success() -> None:
    engine = OllamaCommandEngine(
        "http://127.0.0.1:11435",
        "qwen3.5:4b",
        DevicePreference.GPU,
        resources=ModelResources(memory=lambda: MemorySnapshot()),
        token_counter=lambda payload: 1000,
        transport=lambda url, payload, timeout: (
            {"done": True, "done_reason": "unload"}
            if url.endswith("/api/generate")
            else {
                "prompt_eval_count": 1000,
                "message": {"content": '{"route":"no_action","steps":[]}'},
            }
        ),
        device_probe=lambda url, model: 0,
    )
    with pytest.raises(CommandModelError, match="device"):
        engine.understand(UnderstandingInput("hello", "en"), context=CommandContext())


@pytest.mark.parametrize(
    ("reply", "model_decision", "evidence", "expected"),
    [
        ("oui", "yes", "oui", ConfirmationDecision.YES),
        ("不要", "no", "不要", ConfirmationDecision.NO),
        ("peut-être", "unclear", "peut-être", ConfirmationDecision.UNCLEAR),
        ("oui, mais", "yes", "oui", ConfirmationDecision.UNCLEAR),
    ],
)
def test_ollama_confirmation_requires_the_complete_spoken_reply(
    reply: str,
    model_decision: str,
    evidence: str,
    expected: ConfirmationDecision,
) -> None:
    requests: list[dict[str, object]] = []

    def transport(url: str, payload: dict[str, object], timeout: float) -> object:
        if url.endswith("/api/generate"):
            return {"done": True, "done_reason": "unload"}
        requests.append(payload)
        return {
            "prompt_eval_count": 1000,
            "message": {
                "content": json.dumps(
                    {"decision": model_decision, "evidence": evidence}
                )
            },
        }

    engine = OllamaCommandEngine(
        "http://127.0.0.1:11435",
        "qwen3.5:4b",
        DevicePreference.AUTO,
        resources=ModelResources(memory=lambda: MemorySnapshot()),
        token_counter=lambda payload: 1000,
        transport=transport,
    )
    assert (
        engine.classify_confirmation(
            UnderstandingInput(reply, "fr"), question="Open Telegram?"
        )
        is expected
    )
    schema = requests[0]["format"]
    assert isinstance(schema, dict)
    assert schema["required"] == ["decision", "evidence"]


@pytest.mark.parametrize("source", ["ocr", "accessibility"])
def test_same_process_window_switch_during_inference_keeps_initial_request(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    source: str,
) -> None:
    from threading import Event, Thread
    from time import monotonic
    from typing import Literal, cast

    from kyrin.actions.platforms.desktop_control import DesktopControlExecutor
    from kyrin.desktop.window_observation import WindowObservation

    entered, release = Event(), Event()
    now = monotonic()
    initial = WindowObservation(
        "example.desktop", 42, "window-7", "initial", now, now + 10
    )
    option = VisibleOption(
        "1",
        "Settings",
        cast(Literal["ocr", "accessibility"], source),
        anchor=(75, 42),
        observation=initial,
    )
    token = ["window-7"]

    class SlowModel(FakeModel):
        def understand(
            self, text: UnderstandingInput, *, context: CommandContext
        ) -> UnderstandingResult:
            entered.set()
            assert release.wait(2)
            return super().understand(text, context=context)

    model = SlowModel(_visible_ready("Settings", "1"))
    coordinator = CommandCoordinator(
        _interpreter(
            tmp_path, model, visible_options=(option,), allow_visible_control=True
        ),
        window_observer=lambda: initial,
    )
    events: list[object] = []
    errors: list[BaseException] = []

    def understand() -> None:
        try:
            events.extend(
                coordinator.observe(
                    TranscriptUpdate(
                        0,
                        "Could you click Settings please?",
                        TranscriptStatus.FINAL,
                        "en",
                    ),
                    observed_scroll_app="example.desktop",
                )
            )
        except BaseException as exc:
            errors.append(exc)

    worker = Thread(target=understand)
    worker.start()
    try:
        assert entered.wait(2)
        token[0] = "window-8"  # same app/PID, label, anchor and geometry
    finally:
        release.set()
        worker.join(2)
    assert not worker.is_alive()
    assert errors == []
    resolution = next(event for event in events if isinstance(event, CommandResolution))
    assert resolution.intent is not None
    assert resolution.intent.control_observation is initial
    gate = ActionGate(
        ActionPolicy(
            allow_focused_control=True,
            supported_kinds=frozenset({CommandKind.VISIBLE_CONTROL}),
        )
    )
    request = gate.observe(resolution)
    assert isinstance(request, ActionRequest)
    assert request.intent.control_observation is initial

    class Unused:
        def ready(self) -> bool:
            pytest.fail(
                "changed window must be rejected before locating identical controls"
            )

        def find_visible_control(self, *args: object) -> None:
            pytest.fail("changed window must not be scanned")

        def execute(self, request: ActionRequest) -> ActionResult:
            pytest.fail("must not delegate visible control")

    executor = DesktopControlExecutor(
        Unused(),
        identity_reader=lambda: ("example.desktop", 42),
        token_reader=lambda: token[0],
        verifier=Unused(),
    )
    monkeypatch.setattr(
        "kyrin.actions.platforms.desktop_control.run_process",
        lambda *_a, **_k: pytest.fail("no input"),
    )
    assert (
        executor.execute(request).error_code
        == "visible_control_target_changed:window_token"
    )


def test_discovery_after_first_inference_cannot_replace_initial_window(
    tmp_path: Path,
) -> None:
    from time import monotonic

    from kyrin.desktop.window_observation import WindowObservation

    now = monotonic()
    initial = WindowObservation(
        "example.desktop", 42, "window-7", "initial", now, now + 10
    )
    replaced = WindowObservation(
        "example.desktop", 42, "window-8", "later", now, now + 10
    )
    model = FakeModel(_visible_ready("Search", None))
    coordinator = CommandCoordinator(
        _interpreter(
            tmp_path,
            model,
            allow_visible_control=True,
            visible_options=(
                VisibleOption("1", "Search", "accessibility", observation=replaced),
            ),
        ),
        window_observer=lambda: initial,
    )
    events = coordinator.observe(
        TranscriptUpdate(0, "Search openen", TranscriptStatus.FINAL, "nl"),
        observed_scroll_app="example.desktop",
    )
    assert model.calls == 1
    assert (
        next(event for event in events if isinstance(event, CommandResolution)).intent
        is None
    )
    assert any(
        isinstance(event, ResponseRequest) and event.kind is ResponseKind.REPEAT_COMMAND
        for event in events
    )


def test_model_inference_records_producer_timing_without_source_text(
    tmp_path: Path,
) -> None:
    from kyrin.actions.models import ActionKey
    from kyrin.timing import TimingEvent, TimingScope, timing_scope

    model = FakeModel(_ready(RequestedOperation.OPEN_APP, "telegram"))
    interpreter = _interpreter(tmp_path, model)
    events: list[TimingEvent] = []
    times = iter((1_000_000_000, 1_100_000_000))
    with timing_scope(
        TimingScope("session", ActionKey(2, 3), events.append, lambda: next(times))
    ):
        interpreter.interpret(
            "Por favor abre Telegram",
            language="es",
            context=CommandContext(),
            pending=None,
        )
    assert model.calls == 1
    assert [event.stage for event in events] == [
        "inference_started",
        "inference_finished",
    ]
    assert [event.at_ns for event in events] == [1_000_000_000, 1_100_000_000]
    assert all(event.key == ActionKey(2, 3) for event in events)
    assert "Telegram" not in repr(events)
