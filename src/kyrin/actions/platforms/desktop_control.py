"""Visible text control in any focused app with fresh OCR and input checks."""

import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Protocol

from kyrin.actions.executor import ActionExecutor
from kyrin.actions.models import ActionOutcome, ActionRequest, ActionResult
from kyrin.actions.visible_control import VisibleControlTarget
from kyrin.commands.models import CommandKind
from kyrin.text_normalization import fold_case

CONTROL_HELPER = Path(__file__).with_name("desktop_control_helper.py")
WindowIdentityReader = Callable[[], tuple[str, int] | None]


class VisibleControlVerifier(Protocol):
    def ready(self) -> bool: ...
    def find_visible_control(
        self, app_id: str, pid: int, label: str
    ) -> VisibleControlTarget | None: ...


_SENSITIVE = frozenset(
    {
        "delete",
        "remove",
        "clear",
        "send",
        "submit",
        "buy",
        "purchase",
        "pay",
        "logout",
        "log out",
        "sign out",
        "reset",
        "format",
        "حذف",
        "پاک",
        "ارسال",
        "خرید",
        "پرداخت",
        "خروج",
        "بازنشانی",
    }
)


class DesktopControlExecutor:
    def __init__(
        self,
        delegate: ActionExecutor,
        *,
        identity_reader: WindowIdentityReader,
        verifier: VisibleControlVerifier,
        helper_path: Path = CONTROL_HELPER,
        system_python: str = "/usr/bin/python3",
    ) -> None:
        self._delegate = delegate
        self._identity_reader = identity_reader
        self._verifier = verifier
        self._helper_path = helper_path
        self._system_python = system_python

    def execute(self, request: ActionRequest) -> ActionResult:
        if request.intent.kind is not CommandKind.VISIBLE_CONTROL:
            return self._delegate.execute(request)
        label = request.intent.target.strip()
        normalized = fold_case(label)
        if (
            any(word in normalized.split() for word in _SENSITIVE)
            or normalized in _SENSITIVE
        ):
            return ActionResult(
                request.key,
                ActionOutcome.FAILED,
                error_code="visible_control_sensitive",
            )
        identity = self._identity_reader()
        if identity is None:
            return ActionResult(
                request.key,
                ActionOutcome.FAILED,
                error_code="visible_control_focus_changed",
            )
        if not self._verifier.ready():
            return ActionResult(
                request.key,
                ActionOutcome.FAILED,
                error_code="visible_control_screen_access_required",
            )
        target = self._verifier.find_visible_control(*identity, label)
        if self._identity_reader() != identity:
            return ActionResult(
                request.key,
                ActionOutcome.FAILED,
                error_code="visible_control_focus_changed",
            )
        mode = (
            "click"
            if request.intent.control_state is None
            else "on"
            if request.intent.control_state
            else "off"
        )
        try:
            result = subprocess.run(
                [
                    self._system_python,
                    str(self._helper_path),
                    identity[0],
                    str(identity[1]),
                    *(
                        str(value)
                        for value in (
                            (
                                target.left,
                                target.top,
                                target.width,
                                target.height,
                                target.image_width,
                                target.image_height,
                            )
                            if target is not None
                            else (0, 0, 0, 0, 0, 0)
                        )
                    ),
                    mode,
                    label,
                    "visible" if target is not None else "accessible",
                ],
                capture_output=True,
                text=True,
                timeout=45,
                check=False,
            )
        except OSError, subprocess.TimeoutExpired:
            return ActionResult(
                request.key,
                ActionOutcome.UNKNOWN,
                error_code="visible_control_unavailable",
            )
        if "CONTROL_SETUP_REQUIRED" in result.stdout:
            outcome, reason = ActionOutcome.FAILED, "visible_control_setup_required"
        elif "FOCUS_CHANGED" in result.stdout:
            outcome, reason = ActionOutcome.FAILED, "visible_control_focus_changed"
        elif "TARGET_CHANGED" in result.stdout:
            outcome, reason = ActionOutcome.FAILED, "visible_control_target_changed"
        elif "STATE_UNAVAILABLE" in result.stdout:
            outcome, reason = ActionOutcome.FAILED, "visible_control_state_unavailable"
        elif "TARGET_UNCERTAIN" in result.stdout:
            outcome, reason = ActionOutcome.FAILED, "visible_control_uncertain"
        elif "STATE_ALREADY_SET" in result.stdout:
            outcome, reason = ActionOutcome.CONFIRMED, None
        elif result.returncode == 0 and "CLICK_DISPATCHED" in result.stdout:
            outcome, reason = ActionOutcome.LAUNCH_ACCEPTED, None
        else:
            outcome, reason = ActionOutcome.UNKNOWN, "visible_control_unavailable"
        return ActionResult(request.key, outcome, error_code=reason)
