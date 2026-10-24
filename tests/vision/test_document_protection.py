"""Security regressions use inert checkpoints; no downloaded model is executed."""

from pathlib import Path

import pytest

from kyrin.vision.ocr.backends.document import DocumentOcrEngine, document_model_ready
from kyrin.vision.ocr.backends.tesseract import OcrUnavailableError
from tests.vision.test_document_ocr import _catalog


def test_unknown_checkpoint_is_not_trusted_just_because_files_exist(
    tmp_path: Path,
) -> None:
    models, runtimes = _catalog(tmp_path)
    assert not document_model_ready("surya", models, runtimes)
    with pytest.raises(OcrUnavailableError, match="approved manifest"):
        DocumentOcrEngine("surya", models, runtimes)


@pytest.mark.parametrize("change", ["weights", "extra_code", "symlink", "missing"])
def test_changed_checkpoint_is_rejected_before_worker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, change: str
) -> None:
    from kyrin.vision.ocr.backends import document_trust
    from tests.vision.test_document_protection_fixtures import approve_fixture

    monkeypatch.setattr(document_trust, "APPROVED_MODELS", approve_fixture())
    models, runtimes = _catalog(tmp_path)
    engine = DocumentOcrEngine("surya", models, runtimes)
    model = models / "surya/surya-ocr-2"
    if change == "weights":
        (model / "model.safetensors").write_bytes(b"changed")
    elif change == "extra_code":
        (model / "unknown.py").write_text("# inert fixture")
    elif change == "symlink":
        (model / "model.safetensors").unlink()
        (model / "model.safetensors").symlink_to(model / "config.json")
    else:
        (model / "config.json").unlink()
    monkeypatch.setattr(
        "kyrin.vision.ocr.backends.document.require_sandbox", lambda _command: None
    )

    def unexpected_worker(*_args: object) -> None:
        pytest.fail("Changed model must never execute")

    monkeypatch.setattr(
        "kyrin.vision.ocr.backends.document.run_worker", unexpected_worker
    )
    with pytest.raises(OcrUnavailableError, match="manifest/hash/config"):
        engine.read_text(b"inert")
    assert not document_model_ready("surya", models, runtimes)
    assert not list((runtimes / ".document-work").iterdir())


def test_locally_rehashed_manifest_does_not_authorize_unknown_model(
    tmp_path: Path,
) -> None:
    import hashlib
    import json

    models, runtimes = _catalog(tmp_path)
    model = models / "surya/surya-ocr-2"
    (model / "manifest.json").write_text(
        json.dumps(
            {
                "source": "https://example.org/unverified",
                "files": {"model.safetensors": hashlib.sha256(b"weights").hexdigest()},
            }
        )
    )
    assert not document_model_ready("surya", models, runtimes)


def test_invalid_config_even_with_matching_hash_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from dataclasses import replace
    from hashlib import sha256

    from kyrin.vision.ocr.backends import document_trust
    from tests.vision.test_document_protection_fixtures import approve_fixture

    models, runtimes = _catalog(tmp_path)
    (models / "surya/surya-ocr-2/config.json").write_bytes(b"[]")
    approval = approve_fixture()["surya"]
    approval = replace(
        approval,
        files=(
            ("config.json", sha256(b"[]").hexdigest()),
            approval.files[1],
        ),
    )
    monkeypatch.setattr(document_trust, "APPROVED_MODELS", {"surya": approval})
    assert not document_model_ready("surya", models, runtimes)
    with pytest.raises(OcrUnavailableError, match="config"):
        DocumentOcrEngine("surya", models, runtimes)


def test_snapshot_contains_verified_bytes_after_original_changes(
    tmp_path: Path,
) -> None:
    from kyrin.vision.ocr.backends.document_trust import verify_model
    from tests.vision.test_document_protection_fixtures import approve_fixture

    models, _runtimes = _catalog(tmp_path)
    model = models / "surya/surya-ocr-2"
    snapshot = tmp_path / "snapshot"
    snapshot.mkdir()
    verify_model(model, approve_fixture()["surya"], snapshot)
    (model / "model.safetensors").write_bytes(b"changed after validation")
    assert (snapshot / "model.safetensors").read_bytes() == b"weights"


def test_failed_sandbox_probe_has_no_unprotected_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from subprocess import CompletedProcess
    from unittest.mock import patch

    from kyrin.vision.ocr.backends import document_trust
    from tests.vision.test_document_protection_fixtures import approve_fixture

    monkeypatch.setattr(document_trust, "APPROVED_MODELS", approve_fixture())
    models, runtimes = _catalog(tmp_path)
    engine = DocumentOcrEngine("surya", models, runtimes)
    with (
        patch(
            "kyrin.vision.ocr.backends.document_sandbox.subprocess.run",
            return_value=CompletedProcess([], 1, b"", b"namespace denied"),
        ),
        patch("kyrin.vision.ocr.backends.document.run_worker") as worker,
    ):
        with pytest.raises(OcrUnavailableError, match="protection unavailable"):
            engine.read_text(b"inert")
    worker.assert_not_called()


def test_worker_exit_and_timeout_use_inert_processes(tmp_path: Path) -> None:
    import sys
    from subprocess import TimeoutExpired

    from kyrin.vision.ocr.backends.document_sandbox import run_worker

    result = run_worker([sys.executable, "-I", "-c", "raise SystemExit(7)"], b"")
    assert result.returncode == 7
    with pytest.raises(TimeoutExpired):
        run_worker(
            [sys.executable, "-I", "-c", "import time; time.sleep(60)"],
            b"",
            timeout=0.1,
        )


@pytest.mark.parametrize(
    "field,value",
    [
        ("source", "file:///unknown"),
        ("revision", "main"),
        ("review", ""),
        ("files", (("../outside", "0" * 64),)),
    ],
)
def test_invalid_provenance_or_manifest_is_rejected(
    monkeypatch: pytest.MonkeyPatch, field: str, value: object
) -> None:
    from dataclasses import replace

    from kyrin.vision.ocr.backends import document_trust
    from tests.vision.test_document_protection_fixtures import approve_fixture

    approval = replace(approve_fixture()["surya"], **{field: value})  # type: ignore[arg-type]
    monkeypatch.setattr(document_trust, "APPROVED_MODELS", {"surya": approval})
    with pytest.raises(OcrUnavailableError, match="manifest is invalid"):
        document_trust.approved_model("surya")


def test_worker_descendants_are_killed_on_timeout(tmp_path: Path) -> None:
    import os
    import sys
    import time
    from subprocess import TimeoutExpired

    from kyrin.vision.ocr.backends.document_sandbox import run_worker

    marker = tmp_path / "late-result"
    # Benign child would create a marker after its parent times out.
    child = (
        "import time; from pathlib import Path; time.sleep(.6); "
        f"Path({str(marker)!r}).touch()"
    )
    parent = (
        "import subprocess, sys, time; "
        f"subprocess.Popen([sys.executable, '-I', '-c', {child!r}]); time.sleep(60)"
    )
    with pytest.raises(TimeoutExpired):
        run_worker([sys.executable, "-I", "-c", parent], b"", timeout=0.2)
    time.sleep(0.7)
    assert not marker.exists()
    # The process helper itself must not change the application's environment.
    assert os.environ.get("HOME") != "/tmp/home"


def test_platform_sandbox_enforces_access_or_reports_unavailable(
    tmp_path: Path,
) -> None:
    import json

    from kyrin.vision.ocr.backends.document_sandbox import (
        require_sandbox,
        run_worker,
        sandbox_command,
    )
    from kyrin.vision.ocr.backends.document_trust import DocumentOcrProtectionError

    runtime = tmp_path / "runtime"
    model = tmp_path / "model"
    runtime.mkdir()
    model.mkdir()
    (model / "weights").write_bytes(b"inert")
    secret = tmp_path / "outside-allowlist"
    secret.write_text("inert host marker")
    worker = tmp_path / "probe.py"
    worker.write_text(f"""
import json, os, socket
from pathlib import Path
assert not Path({str(secret)!r}).exists()
assert Path('/model/weights').read_bytes() == b'inert'
try:
    Path('/model/weights').write_bytes(b'changed')
except OSError:
    pass
else:
    raise AssertionError('Model is writable')
assert os.environ.get('DBUS_SESSION_BUS_ADDRESS') is None
try:
    socket.create_connection(('1.1.1.1', 443), timeout=.1)
except OSError:
    pass
else:
    raise AssertionError('External network reachable')
print(json.dumps({{'contained': True}}))
""")
    try:
        command = sandbox_command(runtime, model, worker)
        require_sandbox(command)
    except DocumentOcrProtectionError as error:
        assert "protection unavailable" in str(error)
        return  # Capability denial is an explicit supported, fail-closed result.
    result = run_worker([*command, "--", "/usr/bin/python3", "-I", "/worker.py"], b"")
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {"contained": True}
    assert secret.read_text() == "inert host marker"


def test_worker_resource_limits_are_applied_in_a_benign_child() -> None:
    import json
    import sys

    from kyrin.vision.ocr.backends import document_worker
    from kyrin.vision.ocr.backends.document_sandbox import run_worker

    script = f"""
import json, resource, runpy
worker = runpy.run_path({str(Path(document_worker.__file__).resolve())!r})
worker['_process_limits']()
limits = {{}}
for name in ('RLIMIT_CORE', 'RLIMIT_NOFILE', 'RLIMIT_NPROC',
             'RLIMIT_FSIZE', 'RLIMIT_CPU'):
    limits[name] = resource.getrlimit(getattr(resource, name))
print(json.dumps(limits))
"""
    result = run_worker([sys.executable, "-I", "-c", script], b"")
    assert result.returncode == 0, result.stderr
    limits = json.loads(result.stdout)
    for name, maximum in (
        ("RLIMIT_CORE", 0),
        ("RLIMIT_NOFILE", 128),
        ("RLIMIT_NPROC", 256),
        ("RLIMIT_FSIZE", 16 * 1024 * 1024),
        ("RLIMIT_CPU", 240),
    ):
        soft, hard = limits[name]
        assert 0 <= soft <= hard <= maximum
