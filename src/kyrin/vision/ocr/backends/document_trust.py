"""Reviewed provenance pins, independent of the model directory and its metadata.

An entry is a code-reviewed trust decision, not a locally generated checksum.
No installed document checkpoint currently has independently verified provenance.
"""

import hashlib
import json
import os
import re
import stat
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit

from kyrin.vision.ocr.backends.tesseract import OcrUnavailableError


class DocumentOcrProtectionError(OcrUnavailableError):
    """Provenance or execution containment could not be established."""


@dataclass(frozen=True)
class ApprovedDocumentModel:
    source: str
    revision: str
    review: str
    files: tuple[tuple[str, str], ...]


# Deliberately empty. Never populate this from an unverified installed checkpoint,
# environment variable, or a manifest supplied alongside the model itself.
APPROVED_MODELS: dict[str, ApprovedDocumentModel] = {}


def approved_model(backend: str) -> ApprovedDocumentModel:
    approval = APPROVED_MODELS.get(backend)
    if approval is None:
        raise DocumentOcrProtectionError(
            "Document OCR has no approved manifest/provenance"
        )
    source = urlsplit(approval.source)
    if (
        source.scheme != "https"
        or not source.hostname
        or source.username
        or source.password
        or source.query
        or source.fragment
        or not re.fullmatch(r"[0-9a-f]{40}", approval.revision)
        or not approval.review.strip()
        or not approval.files
    ):
        raise DocumentOcrProtectionError("Document OCR approved manifest is invalid")
    names: set[str] = set()
    for name, digest in approval.files:
        path = PurePosixPath(name)
        if (
            path.is_absolute()
            or ".." in path.parts
            or path.as_posix() != name
            or name in names
            or not re.fullmatch(r"[0-9a-f]{64}", digest)
        ):
            raise DocumentOcrProtectionError(
                "Document OCR approved manifest is invalid"
            )
        names.add(name)
    return approval


def verify_model(
    model: Path, approval: ApprovedDocumentModel, snapshot: Path | None = None
) -> None:
    """Verify exact inventory; when executing, copy and hash the same bytes.

    The private copy closes the ordinary verification/load mutation window.
    Symlinks and special files are rejected, including directory symlinks.
    """
    try:
        if model.is_symlink() or not model.is_dir():
            raise ValueError("Invalid model directory")
        inventory: set[str] = set()
        for path in model.rglob("*"):
            mode = path.lstat().st_mode
            if stat.S_ISDIR(mode):
                continue
            if not stat.S_ISREG(mode):
                raise ValueError("Non-regular model artifact")
            inventory.add(path.relative_to(model).as_posix())
        if inventory != {name for name, _digest in approval.files}:
            raise ValueError("Unexpected or missing artifact")
        for name, expected in approval.files:
            digest = hashlib.sha256()
            # O_NONBLOCK avoids hanging if a file is replaced by a FIFO.
            fd = os.open(model / name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            with os.fdopen(fd, "rb") as source:
                if not stat.S_ISREG(os.fstat(source.fileno()).st_mode):
                    raise ValueError("Non-regular model artifact")
                if snapshot is None:
                    for block in iter(lambda: source.read(1024 * 1024), b""):
                        digest.update(block)
                else:
                    destination = snapshot / name
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    with destination.open("xb") as target:
                        for block in iter(lambda: source.read(1024 * 1024), b""):
                            digest.update(block)
                            target.write(block)
            if digest.hexdigest() != expected:
                raise ValueError("Artifact hash mismatch")
        config = json.loads((snapshot or model).joinpath("config.json").read_bytes())
        if not isinstance(config, dict) or not isinstance(
            config.get("model_type"), str
        ):
            raise ValueError("Invalid model configuration")
        auto_map = config.get("auto_map", {})
        if not isinstance(auto_map, dict) or "--" in json.dumps(auto_map):
            raise ValueError("External model code reference")
    except (OSError, ValueError, TypeError) as error:
        raise DocumentOcrProtectionError(
            "Document OCR model failed approved manifest/hash/config validation"
        ) from error
