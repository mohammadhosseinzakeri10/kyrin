"""Selected vocabulary, complete rendered template and version contract use fakes."""

import io
import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

from kyrin.commands import token_budget


def test_rendered_template_is_tokenized_verbatim_without_weights_or_download(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    binary, blob = tmp_path / "llama-tokenize", tmp_path / "selected.gguf"
    binary.touch()
    calls: list[dict[str, Any]] = []
    template = "<system>قانون</system>\\n<user>اجازه نمی‌دهم</user>\n<assistant>"
    monkeypatch.setattr(token_budget, "local_tokenizer", lambda: binary)
    monkeypatch.setattr(token_budget, "model_blob", lambda store, model: blob)
    monkeypatch.setattr(
        token_budget,
        "urlopen",
        lambda *args, **kwargs: io.BytesIO(b'{"version":"0.31.1"}'),
    )

    def transport(url: str, payload: dict[str, object], timeout: float) -> object:
        calls.append(payload)
        assert payload["_debug_render_only"] is True
        assert payload["truncate"] is False and payload["shift"] is False
        return {"_debug_info": {"rendered_template": template}}

    def run(args: list[str], **kwargs: Any) -> subprocess.CompletedProcess[bytes]:
        assert args[:3] == [str(binary), "--model", str(blob)]
        assert "--offline" in args and "--no-escape" in args and "--stdin" in args
        assert kwargs["input"] == template.encode("utf-8")
        return subprocess.CompletedProcess(args, 0, b"[1, 2, 3, 4, 5]", b"")

    monkeypatch.setattr(token_budget, "run_process", run)
    counter = token_budget.OllamaTokenCounter(
        "http://127.0.0.1:11435", "selected", tmp_path, transport
    )
    assert counter({"messages": [{"role": "user", "content": "اجازه نمی‌دهم"}]}) == 5
    assert len(calls) == 1


def test_unsupported_render_api_never_receives_a_generation_request(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    binary = tmp_path / "llama-tokenize"
    binary.touch()
    monkeypatch.setattr(token_budget, "local_tokenizer", lambda: binary)
    monkeypatch.setattr(
        token_budget,
        "urlopen",
        lambda *args, **kwargs: io.BytesIO(b'{"version":"0.30.0"}'),
    )
    counter = token_budget.OllamaTokenCounter(
        "http://127.0.0.1:11435",
        "selected",
        tmp_path,
        lambda *args: pytest.fail("must not render with unsupported API"),
    )
    with pytest.raises(ValueError, match="version"):
        counter({})


def test_counter_uses_the_exact_selected_manifest_layer(tmp_path: Path) -> None:
    digest = "a" * 64
    config = "b" * 64
    manifest = tmp_path / "manifests/registry.ollama.ai/library/selected/tag"
    manifest.parent.mkdir(parents=True)
    (tmp_path / "blobs").mkdir()
    for name in (digest, config):
        (tmp_path / "blobs" / f"sha256-{name}").touch()
    manifest.write_text(
        json.dumps(
            {
                "config": {"digest": f"sha256:{config}"},
                "layers": [
                    {
                        "mediaType": "application/vnd.ollama.image.model",
                        "digest": f"sha256:{digest}",
                    }
                ],
            }
        )
    )
    assert (
        token_budget.model_blob(tmp_path, "selected:tag")
        == tmp_path / "blobs" / f"sha256-{digest}"
    )
