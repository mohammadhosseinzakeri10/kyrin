"""Packing preserves current evidence and budgets the complete rendered prompt."""

import json
from typing import Any

import pytest

from kyrin.commands.app_names import ModelAppOption
from kyrin.commands.models import CommandContext
from kyrin.commands.ollama_engine import CommandModelError, OllamaCommandEngine
from kyrin.commands.understanding import UnderstandingInput
from kyrin.commands.visible_options import VisibleOption
from kyrin.model_resources import MemorySnapshot, ModelResources
from kyrin.stt.device import DevicePreference


def _engine(
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[OllamaCommandEngine, list[dict[str, Any]]]:
    sent: list[dict[str, Any]] = []

    def transport(url: str, payload: dict[str, Any], timeout: float) -> object:
        sent.append(payload)
        if url.endswith("/api/generate"):
            return {"done": True, "done_reason": "unload"}
        return {
            "prompt_eval_count": len(
                json.dumps(payload["messages"], ensure_ascii=False).encode()
            )
            // 4,
            "message": {"content": '{"route":"no_action","steps":[]}'},
        }

    engine = OllamaCommandEngine(
        "http://127.0.0.1:11435",
        "fake",
        DevicePreference.AUTO,
        transport=transport,
        resources=ModelResources(memory=lambda: MemorySnapshot()),
    )
    # A deterministic tokenizer stands in for the selected model + chat template.
    # Budgeting must call it on the entire serialized request, not option counts.
    monkeypatch.setattr(
        engine,
        "_count_tokens",
        lambda payload: (
            len(json.dumps(payload["messages"], ensure_ascii=False).encode()) // 4
        ),
        raising=False,
    )
    return engine, sent


def test_large_multilingual_catalog_keeps_relevant_late_entry_and_permissions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine, sent = _engine(monkeypatch)
    context = CommandContext(
        available_apps=tuple(
            ModelAppOption(f"app{i}", f"app{i}.desktop", "unrelated " * 20, ())
            for i in range(100)
        )
        + (ModelAppOption("telegram", "telegram.desktop", "Telegram", ("تلگرام",)),),
        available_operations=("open_app", "visible_control"),
        visible_control_enabled=True,
        visible_options=tuple(
            VisibleOption(str(i), f"unrelated control {i}", "ocr") for i in range(100)
        )
        + (VisibleOption("101", "تنظیمات", "accessibility", checked=False),),
        recent_utterances=("never use old consent " * 500,),
    )
    engine.understand(
        UnderstandingInput("تنظیمات تلگرام را باز کن", "fa"), context=context
    )
    payload = next(item for item in sent if "messages" in item)
    options = payload["options"]
    used = len(json.dumps(payload["messages"], ensure_ascii=False).encode()) // 4
    assert used + options["num_predict"] <= options["num_ctx"]
    user = json.loads(payload["messages"][1]["content"])
    assert user["text"] == "تنظیمات تلگرام را باز کن"
    assert user["context"]["available_operations"] == ["open_app", "visible_control"]
    assert user["context"]["permitted_app_ids"] == [
        app.app_id for app in context.available_apps
    ]
    assert user["context"]["visible_control_enabled"] is True
    assert any(app["app_id"] == "telegram" for app in user["context"]["installed_apps"])
    assert any(
        option["option_id"] == "101" for option in user["context"]["visible_options"]
    )
    assert user["context"]["available_visible_actions"] == [
        "click",
        "set_on",
        "set_off",
    ]
    assert payload["truncate"] is False and payload["shift"] is False
    assert payload["keep_alive"] == "30s"
    assert sent[-1] == {"model": "fake", "keep_alive": 0, "stream": False}


def test_oversized_current_evidence_refuses_inference_instead_of_truncating(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine, sent = _engine(monkeypatch)
    with pytest.raises(CommandModelError, match="budget"):
        engine.understand(
            UnderstandingInput("حذف نکن " * 6000, "fa"),
            context=CommandContext(available_operations=()),
        )
    assert not any("messages" in item for item in sent)


def test_confirmation_question_and_reply_are_not_truncated(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine, sent = _engine(monkeypatch)
    with pytest.raises(CommandModelError, match="budget"):
        engine.classify_confirmation(
            UnderstandingInput("نه", "fa"), question="آیا اجازه می‌دهید؟ " * 5000
        )
    assert not any("messages" in item for item in sent)


def test_relevant_ambiguous_controls_are_not_selectively_removed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine, sent = _engine(monkeypatch)
    context = CommandContext(
        available_operations=("visible_control",),
        visible_options=tuple(
            VisibleOption(str(index), "تنظیمات", "ocr") for index in range(400)
        ),
    )
    with pytest.raises(CommandModelError, match="budget"):
        engine.understand(
            UnderstandingInput("تنظیمات را باز کن", "fa"), context=context
        )
    assert not any("messages" in item for item in sent)


def test_actual_token_count_mismatch_rejects_proposal_and_releases_admission(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from kyrin.model_resources import Workload

    engine, sent = _engine(monkeypatch)
    original = engine._transport

    def transport(url: str, payload: dict[str, object], timeout: float) -> object:
        result = original(url, payload, timeout)
        if url.endswith("/api/chat"):
            assert isinstance(result, dict)
            result["prompt_eval_count"] = 1
        return result

    monkeypatch.setattr(engine, "_transport", transport)
    with pytest.raises(CommandModelError, match="token count"):
        engine.understand(UnderstandingInput("hello", "en"), context=CommandContext())
    assert sent[-1]["keep_alive"] == 0
    with engine._resources.use(Workload.STT):
        pass


def test_failed_unload_does_not_admit_a_competing_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from kyrin.model_resources import ResourceUnavailable, Workload

    engine, _ = _engine(monkeypatch)
    original = engine._transport

    def transport(url: str, payload: dict[str, object], timeout: float) -> object:
        if url.endswith("/api/generate"):
            raise TimeoutError("fake unfinished unload")
        return original(url, payload, timeout)

    monkeypatch.setattr(engine, "_transport", transport)
    with pytest.raises(CommandModelError, match="cleanup"):
        engine.understand(UnderstandingInput("hello", "en"), context=CommandContext())
    with pytest.raises(ResourceUnavailable, match="cleanup"):
        with engine._resources.use(Workload.STT):
            pytest.fail("unknown resident model must not be ignored")
