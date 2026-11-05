"""Reuse only real counts of identical fresh templates with unchanged vocabulary."""

import io
import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

from kyrin.commands import token_budget
from kyrin.operations import OperationStopped, budget


@pytest.fixture
def counter_fixture(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[token_budget.OllamaTokenCounter, dict[str, Any]]:
    binary = tmp_path / "llama-tokenize"
    blob = tmp_path / "selected.gguf"
    binary.write_bytes(b"test executable")
    blob.write_bytes(b"test vocabulary")
    state: dict[str, Any] = {
        "prompt": "<system>guard</system><user>اجازه نمی‌دهم</user>",
        "renders": 0,
        "tokenizations": 0,
        "ids": [1, 2, 3],
        "binary": binary,
        "blob": blob,
    }
    monkeypatch.setattr(token_budget, "local_tokenizer", lambda: binary)
    monkeypatch.setattr(token_budget, "model_blob", lambda store, model: blob)
    monkeypatch.setattr(
        token_budget, "urlopen", lambda *a, **kw: io.BytesIO(b'{"version":"0.31.1"}')
    )

    def transport(url: str, payload: dict[str, object], timeout: float) -> object:
        assert payload["_debug_render_only"] is True
        assert payload["truncate"] is False and payload["shift"] is False
        state["renders"] += 1
        return {"_debug_info": {"rendered_template": state["prompt"]}}

    def tokenize(args: list[str], **kwargs: Any) -> subprocess.CompletedProcess[bytes]:
        state["tokenizations"] += 1
        assert kwargs["input"] == state["prompt"].encode("utf-8")
        return subprocess.CompletedProcess(
            args, 0, json.dumps(state["ids"]).encode(), b""
        )

    monkeypatch.setattr(token_budget, "run_process", tokenize)
    counter = token_budget.OllamaTokenCounter(
        "http://127.0.0.1:11435",
        "selected",
        tmp_path,
        transport,
    )
    return counter, state


def test_identical_fresh_templates_reuse_real_count_only(
    counter_fixture: tuple[token_budget.OllamaTokenCounter, dict[str, Any]],
) -> None:
    counter, state = counter_fixture
    assert counter({}) == 3
    assert counter({}) == 3
    assert state["renders"] == 2
    assert state["tokenizations"] == 1
    assert counter.rendered_prompt == state["prompt"]


def test_changed_evidence_is_counted_and_newest_template_is_retained(
    counter_fixture: tuple[token_budget.OllamaTokenCounter, dict[str, Any]],
) -> None:
    counter, state = counter_fixture
    counter({})
    state.update(
        prompt="<user>different permission and window evidence</user>", ids=[1, 2]
    )
    assert counter({}) == 2
    assert state["tokenizations"] == 2
    assert counter.rendered_prompt == state["prompt"]


@pytest.mark.parametrize("file", ["binary", "blob"])
def test_changed_tokenizer_or_vocabulary_invalidates_saved_count(
    counter_fixture: tuple[token_budget.OllamaTokenCounter, dict[str, Any]],
    file: str,
) -> None:
    counter, state = counter_fixture
    counter({})
    state[file].write_bytes(b"replacement with a different identity")
    state["ids"] = [1, 2, 3, 4]
    assert counter({}) == 4
    assert state["tokenizations"] == 2


def test_removed_vocabulary_cannot_reuse_a_previous_count(
    counter_fixture: tuple[token_budget.OllamaTokenCounter, dict[str, Any]],
) -> None:
    counter, state = counter_fixture
    counter({})
    state["blob"].unlink()
    # Fake native call remains usable; a real missing file would fail there.
    assert counter({}) == 3
    assert state["tokenizations"] == 2


def test_invalid_native_counts_are_never_cached(
    counter_fixture: tuple[token_budget.OllamaTokenCounter, dict[str, Any]],
) -> None:
    counter, state = counter_fixture
    state["ids"] = [True]
    with pytest.raises(ValueError, match="invalid token"):
        counter({})
    state["ids"] = [1, 2]
    assert counter({}) == 2
    assert state["tokenizations"] == 2


def test_reuse_has_a_bounded_entry_count(
    counter_fixture: tuple[token_budget.OllamaTokenCounter, dict[str, Any]],
) -> None:
    counter, state = counter_fixture
    for index in range(33):
        state["prompt"] = f"full template {index}"
        counter({})
    counter({})  # newest stays reusable
    assert state["tokenizations"] == 33
    state["prompt"] = "full template 0"
    counter({})  # oldest was evicted
    assert state["tokenizations"] == 34


def test_oversize_utf8_template_is_not_retained(
    counter_fixture: tuple[token_budget.OllamaTokenCounter, dict[str, Any]],
) -> None:
    counter, state = counter_fixture
    state["prompt"] = "فارسی" * 10000
    counter({})
    counter({})
    assert state["tokenizations"] == 2


def test_cancelled_operation_cannot_use_saved_count(
    counter_fixture: tuple[token_budget.OllamaTokenCounter, dict[str, Any]],
) -> None:
    counter, state = counter_fixture
    counter({})
    with budget(5) as operation:
        operation.cancel()
        with pytest.raises(OperationStopped):
            counter({})
    assert state["tokenizations"] == 1
