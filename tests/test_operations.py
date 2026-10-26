"""Deadlines and cancellation retain process ownership and reject late work."""

import os
import signal
import subprocess
import sys
from pathlib import Path
from threading import Event
from typing import Any

import pytest

from kyrin.actions.platforms.helper_lifecycle import HelperLifetime
from kyrin.app.permission_token import read_opaque_token, save_opaque_token
from kyrin.operations import Operation, OperationStopped, activate, budget, run_process


def test_nested_calls_only_receive_remaining_absolute_budget() -> None:
    now = [100.0]
    with budget(10, clock=lambda: now[0]) as outer:
        now[0] += 7
        with budget(18, clock=lambda: now[0]) as inner:
            assert inner.deadline == outer.deadline == 110
            assert inner.remaining() == 3
            now[0] += 3
            with pytest.raises(OperationStopped):
                inner.remaining()
        with pytest.raises(OperationStopped):
            with budget(90, clock=lambda: now[0]):
                pytest.fail("expired parent must not start fallback")


@pytest.mark.parametrize("cause", ["timeout", "cancel", "late_success"])
def test_fake_process_is_terminated_and_reaped_on_stop(
    monkeypatch: pytest.MonkeyPatch,
    cause: str,
) -> None:
    now = [0.0]
    cancel = Event()
    operation = Operation(0.01, lambda: now[0], cancel.is_set)
    calls: list[tuple[bytes | None, float | None]] = []

    class Process:
        pid = 12345
        returncode = None

        def communicate(
            self, input: bytes | None = None, timeout: float | None = None
        ) -> tuple[bytes, bytes]:
            calls.append((input, timeout))
            if len(calls) == 1:
                if cause == "cancel":
                    cancel.set()
                else:
                    now[0] = 1
                if cause == "late_success":
                    self.returncode = 0
                    return b"late", b""
                assert timeout is not None
                raise subprocess.TimeoutExpired("ocr", timeout)
            self.returncode = -15
            return b"", b""

    process = Process()
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: process)
    signals = []
    monkeypatch.setattr(os, "killpg", lambda pid, sig: signals.append(sig))
    with activate(operation), pytest.raises(OperationStopped):
        run_process(["ocr"], timeout=90, input=b"png")
    assert calls[0][1] is not None
    assert calls[0][1] <= 0.01
    assert calls[0][0] == b"png"
    assert len(calls) == 2
    assert signals == [signal.SIGTERM]
    assert process.returncode is not None


def test_kill_after_grace_still_reaps_process(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = []
    operation = Operation(100, lambda: 0)

    class Process:
        pid = 12345
        returncode = None

        def communicate(
            self, input: bytes | None = None, timeout: float | None = None
        ) -> tuple[bytes, bytes]:
            calls.append(timeout)
            if timeout is not None:
                operation.cancel()
                raise subprocess.TimeoutExpired("ocr", timeout)
            self.returncode = -9
            return b"", b""

    process = Process()
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: process)
    signals = []
    monkeypatch.setattr(os, "killpg", lambda pid, sig: signals.append(sig))
    with activate(operation), pytest.raises(OperationStopped):
        run_process(["ocr"], timeout=10)
    assert signals == [signal.SIGTERM, signal.SIGKILL]
    assert calls[-2:] == [0.3, None]
    assert process.returncode == -9


@pytest.mark.parametrize("change", ["unlink", "replace", "deadline"])
def test_input_checks_epoch_and_deadline_immediately_before_dispatch(
    tmp_path: Path,
    change: str,
) -> None:
    path = tmp_path / "control.token"
    save_opaque_token(path, "epoch-one")
    sent: list[tuple[Any, ...]] = []

    class Bus:
        def call_sync(self, *args: object) -> None:
            sent.append(args)

    lifetime = HelperLifetime(Bus(), path, "epoch-one")
    try:
        lifetime.rotate("rotated-one")
        assert read_opaque_token(path) == "rotated-one"
        lifetime.call_sync(
            "bus", "obj", "remote", "NotifyPointerMotion", None, None, 0, 3000, None
        )
        if change == "unlink":
            path.unlink()
        elif change == "replace":
            save_opaque_token(path, "epoch-two")
        else:
            lifetime.operation.cancel()
        with pytest.raises(OperationStopped):
            lifetime.call_sync(
                "bus", "obj", "remote", "NotifyPointerButton", None, None, 0, 3000, None
            )
        # Session cleanup remains possible after cancellation/revocation.
        lifetime.call_sync(
            "bus", "/session", "session", "Close", None, None, 0, 3000, None
        )
        assert [call[3] for call in sent] == ["NotifyPointerMotion", "Close"]
        assert sent[-1][7] == 200
    finally:
        lifetime.close()


def test_revoked_start_cannot_recreate_restore_token(tmp_path: Path) -> None:
    path = tmp_path / "control.token"
    save_opaque_token(path, "epoch-one")
    lifetime = HelperLifetime(None, path, "epoch-one")
    try:
        path.unlink()
        with pytest.raises(OperationStopped):
            lifetime.rotate("late-replacement")
        assert not path.exists()
    finally:
        lifetime.close()


def test_expired_caller_does_not_spawn_a_process(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        subprocess,
        "Popen",
        lambda *a, **k: pytest.fail("must not create an unowned worker"),
    )
    with activate(Operation(0)), pytest.raises(OperationStopped):
        run_process(["ocr"], timeout=90)


def test_helper_authorization_round_trip(
    tmp_path: Path,
) -> None:
    # A real tiny subprocess exercises FD inheritance and the private per-input
    # handshake without GNOME, desktop input, or model runtimes.
    script = tmp_path / "helper.py"
    script.write_text(
        "import os\n"
        "fd = int(os.environ['KYRIN_OPERATION_FD'])\n"
        "os.write(fd, b'?')\n"
        "assert os.read(fd, 1) == b'Y'\n"
        "print('authorized', flush=True)\n"
    )
    result = run_process(
        [sys.executable, str(script)], timeout=2, text=True, helper=True
    )
    assert result.returncode == 0
    assert result.stdout.strip() == "authorized"


def test_cancelled_owner_never_approves_waiting_helper_input(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    operation = Operation(10, lambda: 0)
    endpoints: list[int] = []
    stages: list[str] = []

    class Process:
        pid = 12345
        returncode = None

        def communicate(
            self, input: bytes | None = None, timeout: float | None = None
        ) -> tuple[bytes, bytes]:
            if not stages:
                stages.append("waiting_for_authorization")
                os.write(endpoints[0], b"?")
                operation.cancel()
                assert timeout is not None
                raise subprocess.TimeoutExpired("helper", timeout)
            import select

            assert not select.select([endpoints[0]], [], [], 0)[0]
            os.close(endpoints[0])
            self.returncode = -15
            stages.append("reaped_without_input")
            return b"", b""

    def spawn(*args: object, pass_fds: tuple[int, ...], **kwargs: object) -> Process:
        endpoints.append(os.dup(pass_fds[0]))
        return Process()

    monkeypatch.setattr(subprocess, "Popen", spawn)
    monkeypatch.setattr(os, "killpg", lambda pid, sig: None)
    with activate(operation), pytest.raises(OperationStopped):
        run_process(["helper"], timeout=65, helper=True)
    assert stages == ["waiting_for_authorization", "reaped_without_input"]
