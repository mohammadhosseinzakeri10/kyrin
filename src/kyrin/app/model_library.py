"""Local, engine-aware speech model library independent of the Qt interface."""

import hashlib
import json
import os
import re
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from kyrin.stt.device import ComputeDevice

_VERSION = 1
_GGML_FILE_MAGIC = 0x67676D6C
_DEVICES = {
    "vosk": frozenset({ComputeDevice.CPU}),
    "whisper": frozenset({ComputeDevice.CPU, ComputeDevice.GPU}),
}
_VOSK_NAMED_LANGUAGE = re.compile(r"^vosk-model(?:-small)?-([a-z]{2})(?:-|$)")
_UNSAFE_FOLDER_CHARACTER = re.compile(r"[^a-z0-9._-]+")


class ModelLibraryError(ValueError):
    """An imported model is invalid or cannot be stored safely."""


@dataclass(frozen=True, slots=True)
class InstalledModel:
    model_id: str
    name: str
    backend: str
    language: str
    model_path: Path
    devices: frozenset[ComputeDevice]
    digest: str


def linux_model_library_path() -> Path:
    """Choose the user data location without creating it."""
    configured = os.environ.get("XDG_DATA_HOME")
    root = Path(configured) if configured else Path.home() / ".local" / "share"
    if not root.is_absolute():
        root = Path.home() / ".local" / "share"
    return root / "kyrin" / "models" / "stt"


def vosk_language_hint(source: Path) -> str | None:
    """Suggest the language encoded in an official-style Vosk folder name."""
    match = _VOSK_NAMED_LANGUAGE.match(source.name.lower())
    return match.group(1) if match else None


def _model_directory_name(backend: str, name: str) -> str:
    """Keep imported packages recognizable without losing unique IDs."""
    readable = _UNSAFE_FOLDER_CHARACTER.sub("-", name.lower()).strip("._-")
    prefix = "" if readable.startswith(f"{backend}-") else f"{backend}-"
    return f"{prefix}{readable[:48] or 'model'}-{uuid4().hex}"


def _validate_source(source: Path, backend: str) -> None:
    if source.is_symlink():
        raise ModelLibraryError("Select a model file or directory, not a link")
    if backend == "whisper":
        if not source.is_file() or source.suffix.lower() != ".bin":
            raise ModelLibraryError("Whisper requires a .bin model file")
        try:
            with source.open("rb") as stream:
                if int.from_bytes(stream.read(4), "little") != _GGML_FILE_MAGIC:
                    raise ModelLibraryError("This is not a whisper.cpp model file")
        except OSError as exc:
            raise ModelLibraryError("Whisper model could not be read") from exc
    elif backend == "vosk":
        if not source.is_dir():
            raise ModelLibraryError("Vosk requires an extracted model directory")
        if (
            not (source / "am" / "final.mdl").is_file()
            or not (source / "conf" / "model.conf").is_file()
        ):
            raise ModelLibraryError("Vosk model is missing required files")
        if any(path.is_symlink() for path in source.rglob("*")):
            raise ModelLibraryError("Vosk model directories cannot contain links")
    else:
        raise ModelLibraryError("Unsupported speech model engine")


def _digest(path: Path) -> str:
    fingerprint = hashlib.sha256()
    files = (
        [path] if path.is_file() else sorted(p for p in path.rglob("*") if p.is_file())
    )
    for file in files:
        fingerprint.update(str(file.relative_to(path.parent)).encode("utf-8"))
        fingerprint.update(b"\0")
        with file.open("rb") as stream:
            while chunk := stream.read(1024 * 1024):
                fingerprint.update(chunk)
    return fingerprint.hexdigest()


class ModelLibrary:
    """Copy validated offline models once and derive device views from engines."""

    def __init__(self, root: Path) -> None:
        if not root.is_absolute():
            raise ValueError("model library path must be absolute")
        self.root = root

    def cleanup_incomplete_imports(self) -> None:
        """Remove only our abandoned staging directories at application startup."""
        try:
            for entry in self.root.glob(".import-*"):
                if entry.is_dir() and not entry.is_symlink():
                    shutil.rmtree(entry)
        except OSError as exc:
            raise ModelLibraryError(
                "Incomplete model import could not be cleaned"
            ) from exc

    def list_models(self) -> tuple[InstalledModel, ...]:
        models: list[InstalledModel] = []
        for directory in sorted(self.root.glob("*")):
            if not directory.is_dir() or directory.is_symlink():
                continue
            try:
                document = json.loads(
                    (directory / "model.json").read_text(encoding="utf-8")
                )
                if (
                    not isinstance(document, dict)
                    or set(document)
                    != {"version", "name", "backend", "language", "digest"}
                    or document["version"] != _VERSION
                ):
                    continue
                backend = document["backend"]
                name = document["name"]
                language = document["language"]
                digest = document["digest"]
                if (
                    not isinstance(backend, str)
                    or backend not in _DEVICES
                    or not isinstance(name, str)
                    or not name.strip()
                    or not isinstance(language, str)
                    or not language.strip()
                    or not isinstance(digest, str)
                    or len(digest) != 64
                ):
                    continue
                model_path = directory / (
                    "model.bin" if backend == "whisper" else "model"
                )
                if model_path.is_symlink() or not (
                    model_path.is_file()
                    if backend == "whisper"
                    else model_path.is_dir()
                ):
                    continue
            except OSError, UnicodeError, ValueError:
                continue
            models.append(
                InstalledModel(
                    directory.name,
                    name,
                    backend,
                    language,
                    model_path,
                    _DEVICES[backend],
                    digest,
                )
            )
        return tuple(models)

    def import_model(
        self,
        source: Path,
        *,
        backend: str,
        language: str,
        requested_device: ComputeDevice,
    ) -> InstalledModel:
        """Import into a private staging directory, then publish atomically."""
        if not isinstance(source, Path) or not source.is_absolute():
            raise ModelLibraryError("Choose an absolute model path")
        if not language or any(character.isspace() for character in language):
            raise ModelLibraryError("Enter a language code before importing")
        if backend not in _DEVICES or requested_device not in _DEVICES[backend]:
            raise ModelLibraryError("This engine cannot use the selected device")
        _validate_source(source, backend)
        temporary: Path | None = None
        try:
            self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
            temporary = Path(tempfile.mkdtemp(prefix=".import-", dir=self.root))
            model_path = temporary / ("model.bin" if backend == "whisper" else "model")
            if backend == "whisper":
                shutil.copyfile(source, model_path, follow_symlinks=False)
            else:
                shutil.copytree(source, model_path, symlinks=True)
                if any(path.is_symlink() for path in model_path.rglob("*")):
                    raise ModelLibraryError(
                        "Vosk model directories cannot contain links"
                    )
            digest = _digest(model_path)
            for existing in self.list_models():
                if (
                    existing.backend == backend
                    and existing.digest == digest
                    and (backend == "whisper" or existing.language == language)
                ):
                    return existing
            name = source.stem if backend == "whisper" else source.name
            document = {
                "version": _VERSION,
                "name": name,
                "backend": backend,
                "language": language,
                "digest": digest,
            }
            (temporary / "model.json").write_text(
                json.dumps(document, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            destination = self.root / _model_directory_name(backend, name)
            temporary.rename(destination)
            temporary = None
            return InstalledModel(
                destination.name,
                name,
                backend,
                language,
                destination / model_path.name,
                _DEVICES[backend],
                digest,
            )
        except OSError as exc:
            raise ModelLibraryError("Model could not be imported") from exc
        finally:
            if temporary is not None:
                shutil.rmtree(temporary, ignore_errors=True)
