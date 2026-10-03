"""Launch configured Linux desktop entries without interpreting spoken text."""

import math
import subprocess
from collections.abc import Mapping
from pathlib import Path

from kyrin.actions.models import ActionOutcome, ActionRequest, ActionResult
from kyrin.commands.models import CommandKind


class LinuxDesktopEntryExecutor:
    """Launch known .desktop files; a zero exit code does not verify a window."""

    def __init__(
        self,
        desktop_entries: Mapping[str, Path],
        *,
        timeout_s: float = 5.0,
    ) -> None:
        if not math.isfinite(timeout_s) or timeout_s <= 0:
            raise ValueError("timeout_s must be finite and positive")
        if any(not app_id.strip() for app_id in desktop_entries):
            raise ValueError("app identifiers must not be empty")
        if any(
            not path.is_absolute() or path.suffix != ".desktop"
            for path in desktop_entries.values()
        ):
            raise ValueError("desktop entries must be absolute .desktop paths")
        self._desktop_entries = dict(desktop_entries)
        self._timeout_s = timeout_s

    def execute(self, request: ActionRequest) -> ActionResult:
        if request.intent.kind is not CommandKind.OPEN_APP:
            return ActionResult(
                request.key, ActionOutcome.FAILED, error_code="unsupported_action"
            )

        desktop_entry = self._desktop_entries.get(request.intent.target)
        if desktop_entry is None:
            return ActionResult(
                request.key, ActionOutcome.FAILED, error_code="app_not_configured"
            )
        if not desktop_entry.is_file():
            return ActionResult(
                request.key, ActionOutcome.FAILED, error_code="app_not_installed"
            )

        try:
            completed = subprocess.run(
                ["gio", "launch", str(desktop_entry)],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
                timeout=self._timeout_s,
            )
        except subprocess.TimeoutExpired:
            return ActionResult(
                request.key, ActionOutcome.UNKNOWN, error_code="launcher_timeout"
            )
        except FileNotFoundError:
            return ActionResult(
                request.key, ActionOutcome.FAILED, error_code="launcher_unavailable"
            )
        except PermissionError:
            return ActionResult(
                request.key,
                ActionOutcome.FAILED,
                error_code="launcher_permission_denied",
            )
        except OSError:
            return ActionResult(
                request.key, ActionOutcome.FAILED, error_code="launcher_os_error"
            )

        if completed.returncode != 0:
            return ActionResult(
                request.key, ActionOutcome.FAILED, error_code="launcher_failed"
            )
        return ActionResult(request.key, ActionOutcome.LAUNCH_ACCEPTED)
