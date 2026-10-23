"""Visible text control in any focused app with fresh OCR and input checks."""

import re
import subprocess
import unicodedata
from collections.abc import Callable
from pathlib import Path
from typing import Protocol

from kyrin.actions.executor import ActionExecutor
from kyrin.actions.models import ActionOutcome, ActionRequest, ActionResult
from kyrin.actions.visible_control import VisibleControlTarget
from kyrin.commands.models import CommandKind

CONTROL_HELPER = Path(__file__).with_name("desktop_control_helper.py")
WindowIdentityReader = Callable[[], tuple[str, int] | None]


class VisibleControlVerifier(Protocol):
    def ready(self) -> bool: ...
    def find_visible_control(
        self, app_id: str, pid: int, label: str
    ) -> VisibleControlTarget | None: ...


_CONSEQUENCE_OPERATIONS = {
    "data_loss": re.compile(
        r"\b(?:delete|remove|clear|erase|format|reset)\b|"
        r"(?:حذف|پاک|فرمت|بازنشانی)"
    ),
    "external_effect": re.compile(
        r"\b(?:send|submit|share|post|publish|upload)\b|(?:ارسال|انتشار)"
    ),
    "payment": re.compile(r"\b(?:buy|purchase|pay|checkout)\b|(?:خرید|پرداخت)"),
    "session_exit": re.compile(
        r"\b(?:log out|logout|sign out|signout|quit|exit|close)\b|(?:خروج|بستن)"
    ),
}
_SAFE_NAVIGATION_LABELS = frozenset(
    {"advanced", "settings", "search", "help", "preferences", "about"}
)


def _control_risk(label: str, state: bool | None) -> str | None:
    """Allow known navigation; unknown consequences need confirmation."""
    folded = unicodedata.normalize("NFKC", label).casefold()
    folded = folded.replace("ي", "ی").replace("ك", "ک")
    normalized = "".join(
        " " if unicodedata.category(char).startswith(("P", "S")) else char
        for char in folded
    )
    normalized = " ".join(normalized.split())
    if any(pattern.search(normalized) for pattern in _CONSEQUENCE_OPERATIONS.values()):
        return "visible_control_sensitive"
    if state is None and normalized in _SAFE_NAVIGATION_LABELS:
        return None
    return "visible_control_risk_unknown"


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
        # STT may quote a spoken control name. Those marks describe the name;
        # they are not part of the accessible control's actual label.
        label = request.intent.target.strip().strip('"\'“”‘’«»').strip()
        if not label:
            return ActionResult(
                request.key,
                ActionOutcome.FAILED,
                error_code="visible_control_uncertain",
            )
        risk = _control_risk(label, request.intent.control_state)
        if risk is not None:
            return ActionResult(
                request.key,
                ActionOutcome.FAILED,
                error_code=risk,
            )
        identity = self._identity_reader()
        if identity is None or (
            request.intent.control_window_app is not None
            and identity[0] != request.intent.control_window_app
        ):
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
        target = (
            None
            if request.intent.control_source == "accessibility"
            else self._verifier.find_visible_control(*identity, label)
        )
        if request.intent.control_source == "ocr" and target is None:
            return ActionResult(
                request.key,
                ActionOutcome.FAILED,
                error_code="visible_control_uncertain",
            )
        anchor = request.intent.control_anchor
        if (
            target is not None
            and anchor is not None
            and (
                abs(target.left + target.width // 2 - anchor[0]) > 24
                or abs(target.top + target.height // 2 - anchor[1]) > 24
            )
        ):
            return ActionResult(
                request.key,
                ActionOutcome.FAILED,
                error_code="visible_control_target_changed:ocr_anchor",
            )
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
                    *([str(anchor[0]), str(anchor[1])] if anchor is not None else []),
                    *(
                        [
                            str(value)
                            for value in (*target.capture_rect, *target.frame_rect)
                        ]
                        if target is not None
                        and target.capture_rect is not None
                        and target.frame_rect is not None
                        else []
                    ),
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
        elif "CAPTURE_GEOMETRY_REQUIRED" in result.stdout:
            outcome, reason = (
                ActionOutcome.FAILED,
                "visible_control_capture_geometry_required",
            )
        elif "FOCUS_CHANGED" in result.stdout:
            outcome, reason = ActionOutcome.FAILED, "visible_control_focus_changed"
        elif "TARGET_CHANGED" in result.stdout:
            detail = result.stdout.strip().partition("TARGET_CHANGED:")[2]
            suffix = (
                detail
                if detail in {"frame_size", "pointer_or_window"}
                or re.fullmatch(
                    r"image_scale_\d{1,5}x\d{1,5}_png_\d{1,5}x\d{1,5}",
                    detail,
                )
                else "unknown"
            )
            outcome, reason = (
                ActionOutcome.FAILED,
                f"visible_control_target_changed:{suffix}",
            )
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
