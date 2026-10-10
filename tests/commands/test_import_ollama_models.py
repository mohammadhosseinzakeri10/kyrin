"""Import selected Ollama blobs without altering the source store."""

import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

SCRIPT = (
    Path(__file__).resolve().parents[2] / "scripts/commands/import_ollama_models.py"
)
SPEC = importlib.util.spec_from_file_location("import_ollama_models", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def make_source(root: Path, blob: bytes, *, digest: str | None = None) -> Path:
    source = root / "source"
    checksum = digest or hashlib.sha256(blob).hexdigest()
    blobs = source / "blobs"
    blobs.mkdir(parents=True)
    (blobs / f"sha256-{checksum}").write_bytes(blob)
    manifest = source / "manifests/registry.ollama.ai/library/example/4b"
    manifest.parent.mkdir(parents=True)
    manifest.write_text(
        json.dumps(
            {
                "config": {"digest": f"sha256:{checksum}"},
                "layers": [{"digest": f"sha256:{checksum}"}],
            }
        )
    )
    return source


def test_import_verifies_and_preserves_source(tmp_path: Path) -> None:
    source = make_source(tmp_path, b"model bytes")
    destination = tmp_path / "destination"

    MODULE.import_model(source, destination, "example:4b")

    assert (destination / "manifests/registry.ollama.ai/library/example/4b").is_file()
    assert len(list((destination / "blobs").iterdir())) == 1
    assert (source / "manifests/registry.ollama.ai/library/example/4b").is_file()


def test_bad_hash_never_registers_model(tmp_path: Path) -> None:
    source = make_source(tmp_path, b"corrupt", digest="0" * 64)
    destination = tmp_path / "destination"

    with pytest.raises(ValueError, match="failed SHA-256"):
        MODULE.import_model(source, destination, "example:4b")

    assert not (destination / "manifests").exists()
    assert not list((destination / "blobs").iterdir())
