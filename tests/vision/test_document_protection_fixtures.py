"""Independent test-only approval of inert fixture bytes, not installed models."""

from hashlib import sha256

from kyrin.vision.ocr.backends.document_trust import ApprovedDocumentModel

CONFIG = b'{"model_type":"fixture"}'
WEIGHTS = b"weights"


def approve_fixture() -> dict[str, ApprovedDocumentModel]:
    return {
        "surya": ApprovedDocumentModel(
            source="https://example.org/known-inert-test-fixture",
            revision="1" * 40,
            review="Test-only inert fixture reviewed in source; no real model approval",
            files=(
                ("config.json", sha256(CONFIG).hexdigest()),
                ("model.safetensors", sha256(WEIGHTS).hexdigest()),
            ),
        )
    }
