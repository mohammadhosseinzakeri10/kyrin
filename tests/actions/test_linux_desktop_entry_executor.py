"""Launch outcomes are honest and never construct commands from speech."""

import subprocess
from pathlib import Path

import pytest

from kyrin.actions.executor import ActionExecutor
from kyrin.actions.models import ActionKey, ActionOutcome, ActionRequest, ActionResult
from kyrin.actions.platforms.linux import LinuxDesktopEntryExecutor
from kyrin.commands.models import CommandIntent, CommandKind

OPEN_TELEGRAM = ActionRequest(
    ActionKey(0, 0), CommandIntent(CommandKind.OPEN_APP, "telegram")
)


def test_known_app_launches_only_configured_desktop_entry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    desktop_entry = tmp_path / "telegram.desktop"
    desktop_entry.write_text(
        "[Desktop Entry]\nType=Application\nName=Telegram\nExec=telegram\n"
    )
    calls: list[tuple[list[str], dict[str, object]]] = []

    def fake_run(
        args: list[str], **kwargs: object
    ) -> subprocess.CompletedProcess[bytes]:
        calls.append((args, kwargs))
        return subprocess.CompletedProcess(args, 0)

    monkeypatch.setattr(subprocess, "run", fake_run)
    executor: ActionExecutor = LinuxDesktopEntryExecutor(
        {"telegram": desktop_entry}, timeout_s=1.5
    )
    assert executor.execute(OPEN_TELEGRAM) == ActionResult(
        OPEN_TELEGRAM.key, ActionOutcome.LAUNCH_ACCEPTED
    )
    assert calls == [
        (
            ["gio", "launch", str(desktop_entry)],
            {
                "stdin": subprocess.DEVNULL,
                "stdout": subprocess.DEVNULL,
                "stderr": subprocess.DEVNULL,
                "check": False,
                "timeout": 1.5,
                "start_new_session": True,
            },
        )
    ]


def test_unsupported_or_unconfigured_request_never_calls_launcher(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def forbidden_run(*args: object, **kwargs: object) -> None:
        raise AssertionError("launcher must not be called")

    monkeypatch.setattr(subprocess, "run", forbidden_run)
    executor = LinuxDesktopEntryExecutor({"telegram": tmp_path / "telegram.desktop"})
    chat = ActionRequest(
        ActionKey(0, 1), CommandIntent(CommandKind.OPEN_CHAT, "علی", "telegram")
    )
    assert executor.execute(chat) == ActionResult(
        chat.key, ActionOutcome.FAILED, error_code="unsupported_action"
    )
    unknown_app = ActionRequest(
        ActionKey(0, 2), CommandIntent(CommandKind.OPEN_APP, "unknown")
    )
    assert executor.execute(unknown_app) == ActionResult(
        unknown_app.key, ActionOutcome.FAILED, error_code="app_not_configured"
    )
    assert executor.execute(OPEN_TELEGRAM) == ActionResult(
        OPEN_TELEGRAM.key, ActionOutcome.FAILED, error_code="app_not_installed"
    )


@pytest.mark.parametrize(
    ("failure", "expected_outcome", "error_code"),
    [
        (
            subprocess.CompletedProcess(["gio"], 1),
            ActionOutcome.FAILED,
            "launcher_failed",
        ),
        (FileNotFoundError(), ActionOutcome.FAILED, "launcher_unavailable"),
        (PermissionError(), ActionOutcome.FAILED, "launcher_permission_denied"),
        (OSError(), ActionOutcome.FAILED, "launcher_os_error"),
        (
            subprocess.TimeoutExpired(["gio"], 1),
            ActionOutcome.UNKNOWN,
            "launcher_timeout",
        ),
    ],
)
def test_launcher_failure_is_reported_without_claiming_app_is_active(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure: subprocess.CompletedProcess[bytes] | OSError | subprocess.TimeoutExpired,
    expected_outcome: ActionOutcome,
    error_code: str,
) -> None:
    desktop_entry = tmp_path / "telegram.desktop"
    desktop_entry.write_text(
        "[Desktop Entry]\nType=Application\nName=Telegram\nExec=telegram\n"
    )

    def fake_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        if isinstance(failure, subprocess.CompletedProcess):
            return failure
        raise failure

    monkeypatch.setattr(subprocess, "run", fake_run)
    executor = LinuxDesktopEntryExecutor({"telegram": desktop_entry})
    assert executor.execute(OPEN_TELEGRAM) == ActionResult(
        OPEN_TELEGRAM.key, expected_outcome, error_code=error_code
    )


def test_config_requires_absolute_desktop_paths() -> None:
    with pytest.raises(ValueError, match="absolute"):
        LinuxDesktopEntryExecutor({"telegram": Path("telegram.desktop")})
    with pytest.raises(ValueError, match="timeout"):
        LinuxDesktopEntryExecutor({}, timeout_s=0)
