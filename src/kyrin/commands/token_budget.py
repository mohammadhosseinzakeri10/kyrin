"""Count the selected GGUF's tokens, including Ollama's rendered chat template.

No weight inference, tokenizer download, character/token ratio or remote API.
The render API is version-dependent; unsupported/missing counters fail closed.
"""

import json
import os
import re
import shutil
from collections import OrderedDict
from collections.abc import Callable
from pathlib import Path
from urllib.request import urlopen

from kyrin.commands.ollama_models import ollama_model_stores
from kyrin.operations import check_operation, remaining, run_process

_MAX_COUNT_ENTRIES = 32
_MAX_COUNT_PROMPT_BYTES = 64 * 1024


def _file_identity(path: Path) -> tuple[int, ...]:
    stat = path.stat()
    return (stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns)


def local_tokenizer() -> Path | None:
    explicit = os.environ.get("KYRIN_COMMAND_TOKENIZER")
    if explicit:
        return Path(explicit)
    binary = shutil.which("llama-tokenize")
    if binary:
        return Path(binary)
    # Same installed runtime root as the existing Ubuntu model-library adapter.
    from kyrin.app.model_library import linux_model_library_path

    root = linux_model_library_path().parents[1] / "runtimes/command-understanding"
    candidates = sorted(root.glob("llama.cpp-*/llama-*/llama-tokenize"))
    return candidates[-1] if candidates else None


def model_blob(store: Path, model: str) -> Path:
    selected = ollama_model_stores(store).get(model)
    if selected is None:
        raise ValueError("selected model store is unavailable for tokenization")
    for manifest in (selected / "manifests").rglob("*"):
        if not manifest.is_file():
            continue
        parts = manifest.relative_to(selected / "manifests").parts
        if len(parts) != 4:
            continue
        name = (
            f"{parts[2]}:{parts[3]}"
            if parts[1] == "library"
            else f"{parts[1]}/{parts[2]}:{parts[3]}"
        )
        if name == model:
            document = json.loads(manifest.read_text(encoding="utf-8"))
            for layer in document["layers"]:
                if layer.get("mediaType") == "application/vnd.ollama.image.model":
                    digest = layer["digest"]
                    if (
                        not isinstance(digest, str)
                        or re.fullmatch(r"sha256:[0-9a-f]{64}", digest) is None
                    ):
                        raise ValueError("invalid model digest")
                    return selected / "blobs" / digest.replace(":", "-")
    raise ValueError("selected GGUF vocabulary is unavailable")


class OllamaTokenCounter:
    def __init__(
        self,
        base_url: str,
        model: str,
        store: Path | None,
        transport: Callable[[str, dict[str, object], float], object],
    ) -> None:
        self._base_url, self._model, self._store = base_url, model, store
        self._transport = transport
        self._validated = False
        self._binary: Path | None = None
        self._blob: Path | None = None
        self.rendered_prompt: str | None = None
        # Counts only: rendering and inference remain fresh. No native model is
        # kept resident. The cache belongs to this selected counter/session.
        self._counts: OrderedDict[bytes, int] = OrderedDict()
        self._count_identity: tuple[tuple[int, ...], tuple[int, ...]] | None = None

    def _vocabulary_identity(
        self,
    ) -> tuple[tuple[int, ...], tuple[int, ...]] | None:
        if self._binary is None or self._blob is None:
            return None
        try:
            return (_file_identity(self._binary), _file_identity(self._blob))
        except OSError:
            # Missing/unobservable files must not reuse an old count. Retain
            # the original native error path rather than guessing a count.
            return None

    def __call__(self, payload: dict[str, object]) -> int:
        if not self._validated:
            binary = local_tokenizer()
            if self._store is None or binary is None or not binary.is_file():
                raise ValueError("local command tokenizer is unavailable")
            # Older versions may ignore debug fields and generate instead. Do not
            # send a render request unless the inspected API contract is present.
            with urlopen(
                f"{self._base_url}/api/version", timeout=remaining(3)
            ) as response:
                version = json.load(response).get("version", "")
            parts = str(version).split(".")
            if (
                len(parts) != 3
                or not all(part.isdecimal() for part in parts)
                or tuple(map(int, parts)) < (0, 31, 1)
            ):
                raise ValueError(
                    "Ollama token rendering requires version 0.31.1 or newer"
                )
            self._binary, self._blob = binary, model_blob(self._store, self._model)
            self._validated = True
        rendered = self._transport(
            f"{self._base_url}/api/chat",
            {**payload, "_debug_render_only": True, "truncate": False, "shift": False},
            remaining(120),
        )
        if (
            not isinstance(rendered, dict)
            or not isinstance(debug := rendered.get("_debug_info"), dict)
            or not isinstance(prompt := debug.get("rendered_template"), str)
        ):
            raise ValueError("Ollama did not return an untruncated chat template")
        self.rendered_prompt = prompt
        check_operation()
        encoded = prompt.encode("utf-8")
        identity = self._vocabulary_identity()
        if identity != self._count_identity:
            self._counts.clear()
            self._count_identity = identity
        if identity is not None and (saved := self._counts.get(encoded)) is not None:
            self._counts.move_to_end(encoded)
            return saved
        result = run_process(
            [
                str(self._binary),
                "--model",
                str(self._blob),
                "--stdin",
                "--ids",
                "--no-escape",
                "--offline",
            ],
            input=encoded,
            timeout=10,
        )
        if result.returncode != 0:
            raise ValueError("selected model tokenization failed")
        ids = json.loads(result.stdout)
        if not isinstance(ids, list) or not all(type(token) is int for token in ids):
            raise ValueError("invalid token counter response")
        count = len(ids)
        if (
            identity is not None
            and identity == self._vocabulary_identity()
            and len(encoded) <= _MAX_COUNT_PROMPT_BYTES
            and count > 0
        ):
            self._counts[encoded] = count
            self._counts.move_to_end(encoded)
            if len(self._counts) > _MAX_COUNT_ENTRIES:
                self._counts.popitem(last=False)
        return count
