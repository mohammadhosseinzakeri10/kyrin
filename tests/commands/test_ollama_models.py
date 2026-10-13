"""The selector discovers local tags without trusting incomplete manifests."""

import json
from pathlib import Path

from kyrin.commands.ollama_models import (
    installed_ollama_models,
    ollama_model_stores,
)


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
        / "models/local/by-model/command-understanding/ollama"
    )
    if store.is_dir():
        assert "qwen3.5:4b" in installed_ollama_models(store)


def test_separate_stores_are_discovered_and_resolved(tmp_path: Path) -> None:
    root = tmp_path / "by-model"
    for folder, tag in (("small", "4b"), ("large", "9b")):
        store = root / folder
        manifest = store / "manifests/registry.ollama.ai/library/qwen3.5" / tag
        manifest.parent.mkdir(parents=True)
        digest = tag[0] * 64
        manifest.write_text(
            json.dumps({"config": {"digest": f"sha256:{digest}"}, "layers": []}),
            encoding="utf-8",
        )
        blobs = store / "blobs"
        blobs.mkdir()
        (blobs / f"sha256-{digest}").write_bytes(b"model")
    assert installed_ollama_models(root) == ("qwen3.5:4b", "qwen3.5:9b")
    assert ollama_model_stores(root)["qwen3.5:9b"] == root / "large"


def test_duplicate_tag_is_not_selectable(tmp_path: Path) -> None:
    root = tmp_path / "by-model"
    for folder in ("one", "two"):
        store = root / folder
        manifest = store / "manifests/registry.ollama.ai/library/qwen3.5/4b"
        manifest.parent.mkdir(parents=True)
        digest = "a" * 64
        manifest.write_text(
            json.dumps({"config": {"digest": f"sha256:{digest}"}, "layers": []}),
            encoding="utf-8",
        )
        blobs = store / "blobs"
        blobs.mkdir()
        (blobs / f"sha256-{digest}").write_bytes(b"model")
    assert installed_ollama_models(root) == ()
