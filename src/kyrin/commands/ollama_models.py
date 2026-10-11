"""Discover complete local Ollama tags without loading model weights."""

import json
import re
from pathlib import Path

_DIGEST = re.compile(r"sha256:([0-9a-f]{64})\Z")


def installed_ollama_models(store: Path) -> tuple[str, ...]:
    """Return only tags whose manifest and referenced blobs exist locally."""
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
