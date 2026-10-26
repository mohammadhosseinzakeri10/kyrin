"""Fail-closed Linux document worker containment; offline flags are not a sandbox."""

import os
import signal
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryFile

from kyrin.vision.ocr.backends.document_trust import DocumentOcrProtectionError

_BWRAP = Path("/usr/bin/bwrap")
_MAX_OUTPUT = 1024 * 1024


def sandbox_command(runtime: Path, model: Path, worker: Path) -> list[str]:
    """Expose system libraries and the selected runtime/model only, read-only.

    CPU profile only: no host GPU, session sockets, home or project mount.
    A PID namespace and a new session contain descendants; dropping capabilities
    and disabling nested user namespaces prevent namespace privilege recovery.
    """
    if sys.platform != "linux" or not _BWRAP.is_file():
        raise DocumentOcrProtectionError(
            "Document OCR protection unavailable: Linux/bwrap required"
        )
    command = [
        str(_BWRAP),
        "--unshare-all",
        "--die-with-parent",
        "--new-session",
        "--cap-drop",
        "ALL",
        "--disable-userns",
        "--assert-userns-disabled",
        "--clearenv",
        "--ro-bind",
        "/usr",
        "/usr",
    ]
    for path in ("/lib", "/lib64", "/bin"):
        if Path(path).exists():
            command.extend(["--ro-bind", path, path])
    command.extend(["--dir", "/runtime"])
    # Exclude persistent caches (which can contain Hub credentials), project
    # data and unrelated runtime siblings. Venv Python needs only these paths.
    for name in ("bin", "lib", "lib64", "pyvenv.cfg"):
        runtime_path = runtime / name
        if runtime_path.exists():
            command.extend(["--ro-bind", str(runtime_path), f"/runtime/{name}"])
    command.extend(
        [
            "--ro-bind",
            str(model),
            "/model",
            "--ro-bind",
            str(worker),
            "/worker.py",
            "--proc",
            "/proc",
            "--dev",
            "/dev",
            "--size",
            str(256 * 1024 * 1024),
            "--tmpfs",
            "/tmp",
            "--dir",
            "/tmp/home",
            "--chdir",
            "/tmp",
            "--setenv",
            "HOME",
            "/tmp/home",
            "--setenv",
            "PATH",
            "/usr/bin:/bin",
            "--setenv",
            "HF_HOME",
            "/tmp/cache/huggingface",
            "--setenv",
            "XDG_CACHE_HOME",
            "/tmp/cache",
            "--setenv",
            "HF_HUB_OFFLINE",
            "1",
            "--setenv",
            "TRANSFORMERS_OFFLINE",
            "1",
            "--setenv",
            "OMP_NUM_THREADS",
            "4",
            "--setenv",
            "CUDA_VISIBLE_DEVICES",
            "",
        ]
    )
    return command


def require_sandbox(command: list[str]) -> None:
    """Probe the exact namespace/mount profile without executing model/runtime code."""
    try:
        probe = subprocess.run(
            [*command, "--", "/usr/bin/true"],
            env={},
            stdin=subprocess.DEVNULL,
            capture_output=True,
            timeout=5,
            check=False,
            start_new_session=True,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise DocumentOcrProtectionError(
            "Document OCR protection unavailable: sandbox probe failed"
        ) from error
    if probe.returncode:
        raise DocumentOcrProtectionError(
            "Document OCR protection unavailable: namespaces/mounts denied"
        )


def run_worker(
    command: list[str], image: bytes, *, timeout: float = 240
) -> subprocess.CompletedProcess[bytes]:
    """Bound output memory and kill/reap the process group on timeout or exit."""
    with TemporaryFile() as stdout, TemporaryFile() as stderr:
        with subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=stdout,
            stderr=stderr,
            env={},
            start_new_session=True,
            close_fds=True,
        ) as process:
            try:
                process.communicate(input=image, timeout=timeout)
            finally:
                # Also remove descendants of an exited/crashed launcher. bwrap's
                # PID namespace tears down processes that create another session.
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                process.wait()
            stdout.seek(0)
            stderr.seek(0)
            output = stdout.read(_MAX_OUTPUT + 1)
            errors = stderr.read(_MAX_OUTPUT + 1)
            if len(output) > _MAX_OUTPUT or len(errors) > _MAX_OUTPUT:
                raise DocumentOcrProtectionError(
                    "Document OCR worker output exceeds limit"
                )
            return subprocess.CompletedProcess(
                command, process.returncode, output, errors
            )
