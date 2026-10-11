"""A command model may propose, but original speech and policy still decide."""

from pathlib import Path

import pytest

from kyrin.commands.demo_interpreter import DemoCommandInterpreter
from kyrin.commands.interpreter import ReadyCommand, UnrecognizedCommand
from kyrin.commands.model_interpreter import ModelAssistedInterpreter
from kyrin.commands.models import CommandContext, CommandKind
from kyrin.commands.ollama_engine import CommandModelError, OllamaCommandEngine
from kyrin.commands.understanding import (
    MeaningStep,
    ProposedMeaning,
    RequestedOperation,
    UnderstandingInput,
    UnderstandingResult,
    UnderstandingStatus,
)
from kyrin.desktop.platforms.xdg import XdgDesktopAppCatalog
from kyrin.desktop.spoken_app_names import CatalogSpokenAppResolver
from kyrin.stt.device import DevicePreference


class FakeModel:
    def __init__(self, result: UnderstandingResult | Exception) -> None:
        self.result = result
        self.calls = 0

    def understand(self, source, *, context):  # type: ignore[no-untyped-def]
        self.calls += 1
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def _ready(operation: RequestedOperation, target: str) -> UnderstandingResult:
    return UnderstandingResult(
        UnderstandingStatus.READY,
        (ProposedMeaning((MeaningStep(operation, target),)),),
    )


def _interpreter(tmp_path: Path, model: FakeModel) -> ModelAssistedInterpreter:
    applications = tmp_path / "applications"
    applications.mkdir()
    (applications / "telegram.desktop").write_text(
        "[Desktop Entry]\nType=Application\nName=Telegram\n", encoding="utf-8"
    )
    (applications / "browser.desktop").write_text(
        "[Desktop Entry]\nType=Application\nName=Browser\n", encoding="utf-8"
    )
    names = CatalogSpokenAppResolver(
        XdgDesktopAppCatalog((tmp_path,)),
        {"telegram.desktop": "telegram", "browser.desktop": "browser"},
    )
    return ModelAssistedInterpreter(
        DemoCommandInterpreter(names),
        model,
        names,
        allowed_apps=frozenset({"telegram", "browser"}),
        supported_chat_apps=frozenset(),
    )


def _interpret(interpreter: ModelAssistedInterpreter, text: str, language: str = "en"):
    return interpreter.interpret(
        text, language=language, context=CommandContext(), pending=None
    )


def test_model_handles_a_phrase_not_covered_by_fast_rules(tmp_path: Path) -> None:
    model = FakeModel(_ready(RequestedOperation.OPEN_APP, "Telegram"))
    result = _interpret(_interpreter(tmp_path, model), "Please open Telegram")
    assert isinstance(result, ReadyCommand)
    assert result.intent.kind is CommandKind.OPEN_APP
    assert result.intent.target == "telegram"
    assert model.calls == 1


@pytest.mark.parametrize(
    ("source", "operation", "target", "language"),
    [
        ("Please close Telegram", RequestedOperation.OPEN_APP, "Telegram", "en"),
        ("Please open Telegram", RequestedOperation.OPEN_APP, "Browser", "en"),
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


def test_model_failure_fails_closed(tmp_path: Path) -> None:
    model = FakeModel(CommandModelError("not responding"))
    result = _interpret(_interpreter(tmp_path, model), "Please open Telegram")
    assert isinstance(result, UnrecognizedCommand)


def test_explicit_command_repeats_when_model_claims_no_action(tmp_path: Path) -> None:
    model = FakeModel(UnderstandingResult(UnderstandingStatus.NOT_COMMAND))
    result = _interpret(_interpreter(tmp_path, model), "Please open Telegram")
    assert isinstance(result, UnrecognizedCommand)


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
