"""Copy selected Ollama models into an isolated, hash-verified model store.

This tool never removes source models. After validating the destination with
Ollama, a user can separately remove source tags through `ollama rm`.
"""

import argparse
import hashlib
import json
import os
import re
from pathlib import Path

DIGEST = re.compile(r"^sha256:([0-9a-f]{64})$")
MODEL_PART = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]*$")


def import_model(source: Path, destination: Path, model: str) -> None:
    name, separator, tag = model.partition(":")
    if (
        not separator
        or MODEL_PART.fullmatch(name) is None
        or MODEL_PART.fullmatch(tag) is None
    ):
        raise ValueError(f"invalid Ollama model tag: {model}")
    relative_manifest = Path("registry.ollama.ai/library") / name / tag
    source_manifest = source / "manifests" / relative_manifest
    manifest_bytes = source_manifest.read_bytes()
    manifest = json.loads(manifest_bytes)
    references = [manifest["config"], *manifest["layers"]]
    destination_blobs = destination / "blobs"
    destination_blobs.mkdir(parents=True, exist_ok=True)

    for reference in references:
        digest = reference["digest"]
        match = DIGEST.fullmatch(digest)
        if match is None:
            raise ValueError(f"unexpected blob digest: {digest}")
        filename = digest.replace(":", "-", 1)
        source_blob = source / "blobs" / filename
        target_blob = destination_blobs / filename
        if source_blob.is_symlink() or not source_blob.is_file():
            raise ValueError(f"source blob is not a regular file: {source_blob}")
        if target_blob.exists() and verify_blob(target_blob, match.group(1)):
            print(f"Already verified: {filename}", flush=True)
            continue
        temporary_blob = destination_blobs / f".{filename}.copying"
        try:
            checksum = hashlib.sha256()
            with (
                source_blob.open("rb") as input_file,
                temporary_blob.open("wb") as output,
            ):
                while chunk := input_file.read(16 * 1024 * 1024):
                    output.write(chunk)
                    checksum.update(chunk)
                output.flush()
                os.fsync(output.fileno())
            if checksum.hexdigest() != match.group(1):
                raise ValueError(f"source blob failed SHA-256 check: {source_blob}")
            os.replace(temporary_blob, target_blob)
        finally:
            temporary_blob.unlink(missing_ok=True)
        print(f"Copied and verified: {filename}", flush=True)

    target_manifest = destination / "manifests" / relative_manifest
    target_manifest.parent.mkdir(parents=True, exist_ok=True)
    temporary_manifest = target_manifest.with_name(f".{tag}.copying")
    try:
        temporary_manifest.write_bytes(manifest_bytes)
        os.replace(temporary_manifest, target_manifest)
    finally:
        temporary_manifest.unlink(missing_ok=True)
    print(f"Model ready: {model}", flush=True)


def verify_blob(path: Path, expected_hex: str) -> bool:
    checksum = hashlib.sha256()
    with path.open("rb") as blob:
        for chunk in iter(lambda: blob.read(16 * 1024 * 1024), b""):
            checksum.update(chunk)
    return checksum.hexdigest() == expected_hex


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--destination", type=Path, required=True)
    parser.add_argument("--model", action="append", required=True)
    args = parser.parse_args()
    if args.source.resolve() == args.destination.resolve():
        parser.error("source and destination must differ")
    for model in args.model:
        import_model(args.source, args.destination, model)


if __name__ == "__main__":
    main()
