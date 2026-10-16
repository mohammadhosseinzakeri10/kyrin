"""One bounded scroll in the focused, explicitly permitted desktop app."""

import subprocess
from collections.abc import Callable, Mapping
from pathlib import Path

from kyrin.actions.executor import ActionExecutor
from kyrin.actions.models import ActionOutcome, ActionRequest, ActionResult
from kyrin.commands.models import CommandKind

SCROLL_HELPER = Path(__file__).with_name("desktop_scroll_helper.py")
WindowIdentityReader = Callable[[], tuple[str, int] | None]


class DesktopScrollExecutor:
    def __init__(
        self,
        delegate: ActionExecutor,
        *,
        desktop_ids: Mapping[str, str],
        identity_reader: WindowIdentityReader,
        helper_path: Path = SCROLL_HELPER,
        system_python: str = "/usr/bin/python3",
    ) -> None:
        self._delegate = delegate
        self._desktop_ids = dict(desktop_ids)
        self._identity_reader = identity_reader
        self._helper_path = helper_path
        self._system_python = system_python

    def execute(self, request: ActionRequest) -> ActionResult:
        kind = request.intent.kind
        if kind not in (CommandKind.SCROLL_UP, CommandKind.SCROLL_DOWN):
            return self._delegate.execute(request)
        desktop_id = self._desktop_ids.get(request.intent.target)
        identity = self._identity_reader()
        if desktop_id is None or identity is None or identity[0] != desktop_id:
            return ActionResult(
                request.key, ActionOutcome.FAILED, error_code="scroll_focus_changed"
            )
        try:
            completed = subprocess.run(
                [
                    self._system_python,
                    str(self._helper_path),
                    identity[0],
                    str(identity[1]),
                    "up" if kind is CommandKind.SCROLL_UP else "down",
                    str(request.intent.scroll_steps or 3),
                    "left" if request.intent.target == "telegram" else "center",
                    "desktop-scroll",
                ],
                capture_output=True,
                text=True,
                timeout=45,
                check=False,
            )
        except OSError, subprocess.TimeoutExpired:
            return ActionResult(
                request.key, ActionOutcome.UNKNOWN, error_code="scroll_unavailable"
            )
        if "CONTROL_SETUP_REQUIRED" in completed.stdout:
            return ActionResult(
                request.key,
                ActionOutcome.FAILED,
                error_code="scroll_control_setup_required",
            )
        if completed.returncode == 0 and "SCROLL_DISPATCHED" in completed.stdout:
            return ActionResult(
                request.key,
                ActionOutcome.LAUNCH_ACCEPTED,
            )
        return ActionResult(
            request.key, ActionOutcome.UNKNOWN, error_code="scroll_unavailable"
        )
