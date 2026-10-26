"""Discover complete local Ollama tags without loading model weights."""

import json
import re
from pathlib import Path

_DIGEST = re.compile(r"sha256:([0-9a-f]{64})\Z")


def _store_models(store: Path) -> tuple[str, ...]:
    """Read a single Ollama store without loading its model weights."""
    if not store.is_absolute() or store.is_symlink():
        return ()
    root = store / "manifests"
    if not root.is_dir() or root.is_symlink():
        return ()
    names: set[str] = set()
    for manifest in root.rglob("*"):
        if not manifest.is_file() or manifest.is_symlink():
            continue
        relative = manifest.relative_to(root).parts
        if len(relative) != 4 or any(part.startswith(".") for part in relative):
            continue
        try:
            document = json.loads(manifest.read_text(encoding="utf-8"))
            references = [document["config"], *document["layers"]]
            digests = [item["digest"] for item in references]
        except OSError, UnicodeError, ValueError, KeyError, TypeError:
            continue
        if not digests or any(
            not isinstance(digest, str)
            or (match := _DIGEST.fullmatch(digest)) is None
            or not (store / "blobs" / f"sha256-{match[1]}").is_file()
            for digest in digests
        ):
            continue
        namespace, repository, tag = relative[1:]
        name = (
            f"{repository}:{tag}"
            if namespace == "library"
            else f"{namespace}/{repository}:{tag}"
        )
        names.add(name)
    return tuple(sorted(names))


def ollama_model_stores(location: Path) -> dict[str, Path]:
    """Map tags to complete stores in a store or a per-model directory.

    A tag present in two child stores is ambiguous and is omitted rather than
    depending on directory traversal order.
    """
    if not location.is_absolute() or location.is_symlink():
        return {}
    if (location / "manifests").is_dir():
        return {name: location for name in _store_models(location)}
    stores: dict[str, Path] = {}
    duplicates: set[str] = set()
    if not location.is_dir():
        return stores
    for child in sorted(location.iterdir()):
        if not child.is_dir() or child.is_symlink():
            continue
        for name in _store_models(child):
            if name in stores:
                duplicates.add(name)
            else:
                stores[name] = child
    for name in duplicates:
        del stores[name]
    return stores


def installed_ollama_models(location: Path) -> tuple[str, ...]:
    """Discover complete tags in one store or separate model stores."""
    return tuple(sorted(ollama_model_stores(location)))
