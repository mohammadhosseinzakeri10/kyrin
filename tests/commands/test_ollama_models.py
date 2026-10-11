"""The selector discovers local tags without trusting incomplete manifests."""

import json
from pathlib import Path

from kyrin.commands.ollama_models import installed_ollama_models


def test_only_complete_local_model_is_discovered(tmp_path: Path) -> None:
    store = tmp_path / "ollama"
    root = store / "manifests/registry.ollama.ai/library/qwen3.5"
    root.mkdir(parents=True)
    digest = "a" * 64
    manifest = {"config": {"digest": f"sha256:{digest}"}, "layers": []}
    (root / "4b").write_text(json.dumps(manifest), encoding="utf-8")
    assert installed_ollama_models(store) == ()
    blobs = store / "blobs"
    blobs.mkdir()
    (blobs / f"sha256-{digest}").write_bytes(b"model")
    assert installed_ollama_models(store) == ("qwen3.5:4b",)


def test_current_project_models_are_discoverable() -> None:
    store = (
        Path(__file__).resolve().parents[2]
        / "models/local/command-understanding/ollama"
    )
    if store.is_dir():
        assert "qwen3.5:4b" in installed_ollama_models(store)
