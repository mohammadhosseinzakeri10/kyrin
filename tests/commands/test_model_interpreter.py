"""A command model may propose, but original speech and policy still decide."""

import json
from pathlib import Path

import pytest

from kyrin.commands.app_names import SpokenAppCandidate
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
from kyrin.desktop.platforms.xdg import XdgDesktopAppCatalog
from kyrin.desktop.spoken_app_names import CatalogSpokenAppResolver
from kyrin.desktop.window_presence import WindowPresence
from kyrin.responses.presenter import ResponsePresenter
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
) -> ModelAssistedInterpreter:
    applications = tmp_path / "applications"
    applications.mkdir()
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
    return ModelAssistedInterpreter(
        DemoCommandInterpreter(names),
        model,
        names,
        allowed_apps=frozenset({"telegram", "browser", "visual-studio-code"}),
        supported_chat_apps=supported_chat_apps,
        allow_visible_control=allow_visible_control,
        visible_options_reader=(
            FakeVisibleOptionsReader(visible_options) if allow_visible_control else None
        ),
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
    spoken_target: str, option_id: str, state: bool | None = None
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


def test_natural_request_uses_screen_option_id_to_correct_spelling(
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

    assert result == ReadyCommand(
        CommandIntent(
            CommandKind.VISIBLE_CONTROL,
            "Settings",
            control_source="accessibility",
            control_anchor=(75, 42),
        )
    )
    assert model.last_context is not None
    assert model.last_context.visible_options == (option,)


def test_natural_state_request_requires_matching_screen_option_and_direction(
    tmp_path: Path,
) -> None:
    option = VisibleOption("2", "Notifications", "accessibility", "switch", True)
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
        )
    )
    model.result = _visible_ready("Notifications", "2", True)
    assert isinstance(
        interpreter.interpret(
            "I want Notifications off", language="en", context=context, pending=None
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
            CommandKind.VISIBLE_CONTROL, "Search", control_source="accessibility"
        )
    )


def _interpret(
    interpreter: ModelAssistedInterpreter, text: str, language: str = "en"
) -> Interpretation:
    return interpreter.interpret(
        text, language=language, context=CommandContext(), pending=None
    )


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
        requests.append(payload)
        return {"message": {"content": '{"route":"no_action","steps":[]}'}}

    for device, expected in (
        (DevicePreference.CPU, 0),
        (DevicePreference.GPU, 999),
        (DevicePreference.AUTO, None),
    ):
        engine = OllamaCommandEngine(
            "http://127.0.0.1:11435",
            "qwen3.5:4b",
            device,
            transport=transport,
            device_probe=lambda url, model, selected=device: (
                0 if selected is DevicePreference.CPU else 1024
            ),
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
        request.update(payload)
        return {
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
            }
        }

    engine = OllamaCommandEngine(
        "http://127.0.0.1:11435",
        "qwen3.5:4b",
        DevicePreference.AUTO,
        transport=transport,
    )
    result = engine.understand(
        UnderstandingInput("open seating", "en"),
        context=CommandContext(
            visible_options=(VisibleOption("1", "Settings", "accessibility"),)
        ),
    )
    assert result.candidates[0].steps[0].target_id == "1"
    messages = request["messages"]
    assert isinstance(messages, list)
    user = json.loads(messages[1]["content"])
    assert user["context"]["visible_options"][0]["label"] == "Settings"
    assert user["context"]["available_visible_actions"] == ["click"]


def test_explicit_gpu_without_gpu_memory_does_not_claim_success() -> None:
    engine = OllamaCommandEngine(
        "http://127.0.0.1:11435",
        "qwen3.5:4b",
        DevicePreference.GPU,
        transport=lambda url, payload, timeout: {
            "message": {"content": '{"route":"no_action","steps":[]}'},
        },
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
        requests.append(payload)
        return {
            "message": {
                "content": json.dumps(
                    {"decision": model_decision, "evidence": evidence}
                )
            }
        }

    engine = OllamaCommandEngine(
        "http://127.0.0.1:11435",
        "qwen3.5:4b",
        DevicePreference.AUTO,
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
