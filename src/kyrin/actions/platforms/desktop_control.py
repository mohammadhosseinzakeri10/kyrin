"""Focused controls via AT-SPI Action, with a guarded coordinate fallback."""

import json
import re
import subprocess
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from time import monotonic
from typing import Protocol

from kyrin.actions.cancellation import execute_with_budget
from kyrin.actions.control_policy import (
    ControlApproval,
    ControlCapability,
    ControlConfirmation,
    ControlConfirmer,
    ControlConsequence,
    ControlEvidence,
    control_policy,
)
from kyrin.actions.executor import ActionExecutor
from kyrin.actions.models import ActionOutcome, ActionRequest, ActionResult
from kyrin.actions.visible_control import VisibleControlTarget
from kyrin.backend_protocol import BackendUnavailable
from kyrin.commands.models import CommandKind
from kyrin.desktop.accessibility_target import AccessibilityTarget
from kyrin.desktop.platforms.gnome import read_active_window_token
from kyrin.operations import check_operation, run_process

CONTROL_HELPER = Path(__file__).with_name("desktop_control_helper.py")
WindowIdentityReader = Callable[[], tuple[str, int] | None]


class VisibleControlVerifier(Protocol):
    def ready(self) -> bool: ...
    def find_visible_control(
        self, app_id: str, pid: int, label: str
    ) -> VisibleControlTarget | None: ...


_TARGET_CHANGED_CODES = frozenset(
    {
        "content",
        "window_token",
        "stale_capture",
        "stale_or_window",
        "frame_size",
        "pointer_or_window",
    }
)
_IMAGE_SCALE_CODE = re.compile(r"image_scale_\d{1,5}x\d{1,5}_png_\d{1,5}x\d{1,5}")


def _control_risk(label: str, state: bool | None) -> str | None:
    """Compatibility error mapping; authority comes from trusted capabilities."""
    _, consequence = control_policy(label, state)
    if consequence is ControlConsequence.UNSUPPORTED:
        return "visible_control_sensitive"
    if consequence is ControlConsequence.UNKNOWN:
        return "visible_control_risk_unknown"
    return None


class DesktopControlExecutor:
    def __init__(
        self,
        delegate: ActionExecutor,
        *,
        identity_reader: WindowIdentityReader,
        verifier: VisibleControlVerifier | None = None,
        helper_path: Path = CONTROL_HELPER,
        system_python: str = "/usr/bin/python3",
        token_reader: Callable[[], str | None] | None = None,
        confirmation: ControlConfirmer | None = None,
        control_resolver: Callable[
            [ActionRequest, tuple[str, int], str], ControlEvidence | None
        ]
        | None = None,
        capabilities: frozenset[ControlCapability] = frozenset(ControlCapability),
    ) -> None:
        self._delegate = delegate
        self._identity_reader = identity_reader
        self._token_reader = token_reader or read_active_window_token
        self._verifier = verifier
        self._helper_path = helper_path
        self._system_python = system_python
        self._confirmation = confirmation
        self._resolve = control_resolver or self._resolve_control
        self._capabilities = capabilities

    def execute(self, request: ActionRequest) -> ActionResult:
        observation = request.intent.control_observation
        timeout = (
            min(45.0, max(0.001, observation.deadline - monotonic()))
            if observation is not None
            else 45.0
        )
        return execute_with_budget(
            request, lambda: self._execute(request), timeout_s=timeout
        )

    def _resolve_control(
        self, request: ActionRequest, identity: tuple[str, int], label: str
    ) -> ControlEvidence | None:
        """Observe independently of language-model options, without any input."""
        observation = request.intent.control_observation
        assert observation is not None
        if request.intent.control_source != "ocr":
            try:
                result = run_process(
                    [
                        self._system_python,
                        str(
                            CONTROL_HELPER.with_name(
                                "desktop_accessibility_inventory.py"
                            )
                        ),
                        identity[0],
                        str(identity[1]),
                        observation.window_token,
                    ],
                    capture_output=True,
                    text=True,
                    timeout=6,
                    check=False,
                )
                payload = json.loads(result.stdout) if result.returncode == 0 else []
                if not isinstance(payload, list):
                    return None
                matches = [
                    item
                    for item in payload
                    if isinstance(item, dict)
                    and str(item.get("label", "")).casefold() == label.casefold()
                ]
                if matches:
                    if len(matches) != 1:
                        return None
                    item = matches[0]
                    target = AccessibilityTarget.from_json(item["accessibility"])
                    checked, role = item.get("checked"), item.get("role")
                    x, y = item.get("x"), item.get("y")
                    if (
                        not isinstance(role, str)
                        or (checked is not None and type(checked) is not bool)
                        or type(x) is not int
                        or type(y) is not int
                        or min(x, y) < 0
                    ):
                        return None
                    return ControlEvidence(
                        label, "accessibility", role, checked, (x, y), target
                    )
            except OSError, subprocess.TimeoutExpired, ValueError, KeyError, TypeError:
                return None
        if (
            request.intent.control_source == "accessibility"
            or request.intent.control_state is not None
            or self._verifier is None
            or not self._verifier.ready()
        ):
            return None
        target_box = self._verifier.find_visible_control(*identity, label)
        if (
            target_box is None
            or target_box.geometry is None
            or target_box.geometry.window_token != observation.window_token
        ):
            return None
        return ControlEvidence(
            label,
            "ocr",
            None,
            None,
            (
                target_box.left + target_box.width // 2,
                target_box.top + target_box.height // 2,
            ),
            bounds=(
                target_box.left,
                target_box.top,
                target_box.width,
                target_box.height,
                target_box.image_width,
                target_box.image_height,
                *(target_box.capture_rect or ()),
                *(target_box.frame_rect or ()),
            ),
        )

    def _confirm_control(
        self,
        request: ActionRequest,
        identity: tuple[str, int],
        label: str,
        capability: ControlCapability,
    ) -> tuple[ActionRequest, ControlEvidence] | ActionResult:
        observation = request.intent.control_observation
        assert observation is not None and self._confirmation is not None

        def failure(reason: str) -> ActionResult:
            return ActionResult(request.key, ActionOutcome.FAILED, error_code=reason)

        target = self._resolve(request, identity, label)
        if target is None or target.label != label:
            return failure("visible_control_uncertain")
        if (
            request.intent.control_accessibility is not None
            and target.accessibility != request.intent.control_accessibility
        ) or (
            request.intent.control_anchor is not None
            and target.anchor != request.intent.control_anchor
        ):
            return failure("visible_control_target_changed")
        if request.intent.control_state is not None and (
            target.checked is None or target.accessibility is None
        ):
            return failure("visible_control_state_unavailable")
        if not observation.current(self._token_reader(), monotonic()) or (
            self._identity_reader() != identity
        ):
            return failure("visible_control_target_changed")
        prompt = ControlConfirmation(
            request.key,
            capability,
            target,
            observation,
            request.intent.control_state,
            request.language,
        )
        check_operation()
        if self._confirmation(prompt) is not True:
            return failure("visible_control_confirmation_declined")
        approval = ControlApproval(prompt)
        check_operation()
        if not observation.current(self._token_reader(), monotonic()) or (
            self._identity_reader() != identity
        ):
            return failure("visible_control_confirmation_expired")
        fresh = self._resolve(request, identity, label)
        if (
            fresh is None
            or fresh.source == "window"
            or not approval.consume(replace(prompt, target=fresh), monotonic())
        ):
            return failure("visible_control_target_changed")
        if self._identity_reader() != identity or not observation.current(
            self._token_reader(), monotonic()
        ):
            return failure("visible_control_target_changed")
        return (
            replace(
                request,
                intent=replace(
                    request.intent,
                    control_source=fresh.source,
                    control_anchor=fresh.anchor,
                    control_accessibility=fresh.accessibility,
                ),
            ),
            fresh,
        )

    def _try_accessible(
        self,
        request: ActionRequest,
        identity: tuple[str, int],
        label: str,
        consent: ControlEvidence | None = None,
    ) -> ActionResult | None:
        observation = request.intent.control_observation
        assert observation is not None
        mode = (
            "click"
            if request.intent.control_state is None
            else "on"
            if request.intent.control_state
            else "off"
        )
        try:
            result = run_process(
                [
                    self._system_python,
                    str(self._helper_path),
                    "semantic",
                    identity[0],
                    str(identity[1]),
                    mode,
                    label,
                    observation.to_json(),
                    *self._consent_argument(consent),
                    *(
                        [request.intent.control_accessibility.to_json()]
                        if request.intent.control_accessibility is not None
                        else []
                    ),
                ],
                helper=True,
                helper_capabilities={"desktop_control-v1"},
                capture_output=True,
                text=True,
                timeout=45,
                check=False,
            )
        except BackendUnavailable as error:
            return ActionResult(
                request.key,
                ActionOutcome.FAILED,
                error_code="backend:" + error.status.reason,
            )
        except OSError, subprocess.TimeoutExpired:
            return ActionResult(
                request.key,
                ActionOutcome.UNKNOWN,
                error_code="visible_control_unavailable",
            )
        if result.returncode == 0 and result.stdout.strip() == "NO_ACCESSIBLE_ACTION":
            return None
        return self._helper_result(request, result)

    def _execute(self, request: ActionRequest) -> ActionResult:
        if request.intent.kind is not CommandKind.VISIBLE_CONTROL:
            return self._delegate.execute(request)
        # STT may quote a spoken control name. Those marks describe the name;
        # they are not part of the accessible control's actual label.
        label = request.intent.target.strip().strip("\"'“”‘’«»").strip()
        if not label:
            return ActionResult(
                request.key,
                ActionOutcome.FAILED,
                error_code="visible_control_uncertain",
            )
        capability, consequence = control_policy(label, request.intent.control_state)
        risk = _control_risk(label, request.intent.control_state)
        if capability not in self._capabilities:
            risk = "visible_control_capability_required"
        if risk is not None and (
            consequence is not ControlConsequence.UNKNOWN
            or self._confirmation is None
            or capability not in self._capabilities
        ):
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
        observation = request.intent.control_observation
        if observation is None or self._token_reader() != observation.window_token:
            return ActionResult(
                request.key,
                ActionOutcome.FAILED,
                error_code="visible_control_target_changed:window_token",
            )
        if identity != observation.identity:
            return ActionResult(
                request.key,
                ActionOutcome.FAILED,
                error_code="visible_control_focus_changed",
            )
        if not observation.current(observation.window_token, monotonic()):
            return ActionResult(
                request.key,
                ActionOutcome.FAILED,
                error_code="visible_control_target_changed:stale_capture",
            )
        consent: ControlEvidence | None = None
        if consequence is ControlConsequence.UNKNOWN:
            authorized = self._confirm_control(request, identity, label, capability)
            if isinstance(authorized, ActionResult):
                return authorized
            request, consent = authorized
        semantic = (
            self._try_accessible(request, identity, label, consent)
            if request.intent.control_source != "ocr"
            else None
        )
        if semantic is not None:
            return semantic
        if request.intent.control_source != "accessibility" and (
            self._verifier is None or not self._verifier.ready()
        ):
            return ActionResult(
                request.key,
                ActionOutcome.FAILED,
                error_code="visible_control_screen_access_required",
            )
        target = (
            None
            if request.intent.control_source == "accessibility"
            or self._verifier is None
            else self._verifier.find_visible_control(*identity, label)
        )
        if request.intent.control_source == "ocr" and target is None:
            return ActionResult(
                request.key,
                ActionOutcome.FAILED,
                error_code="visible_control_uncertain",
            )
        if target is not None and (
            target.geometry is None
            or target.geometry.window_token != observation.window_token
        ):
            return ActionResult(
                request.key,
                ActionOutcome.FAILED,
                error_code="visible_control_target_changed:window_token",
            )
        if consent is not None and consent.source == "ocr" and target is not None:
            bounds = (
                target.left,
                target.top,
                target.width,
                target.height,
                target.image_width,
                target.image_height,
                *(target.capture_rect or ()),
                *(target.frame_rect or ()),
            )
            if bounds != consent.bounds:
                return ActionResult(
                    request.key,
                    ActionOutcome.FAILED,
                    error_code="visible_control_target_changed",
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
        if not observation.current(self._token_reader(), monotonic()):
            return ActionResult(
                request.key,
                ActionOutcome.FAILED,
                error_code="visible_control_target_changed:stale_or_window",
            )
        mode = (
            "click"
            if request.intent.control_state is None
            else "on"
            if request.intent.control_state
            else "off"
        )
        try:
            result = run_process(
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
                    *self._consent_argument(consent),
                    "observation=" + observation.to_json(),
                    *(
                        [
                            "accessibility="
                            + request.intent.control_accessibility.to_json()
                        ]
                        if request.intent.control_accessibility is not None
                        else []
                    ),
                    *(
                        ["geometry=" + target.geometry.to_json()]
                        if target is not None and target.geometry is not None
                        else []
                    ),
                ],
                helper=True,
                helper_capabilities={"desktop_control-v1"},
                capture_output=True,
                text=True,
                timeout=45,
                check=False,
            )
        except BackendUnavailable as error:
            return ActionResult(
                request.key,
                ActionOutcome.FAILED,
                error_code="backend:" + error.status.reason,
            )
        except OSError, subprocess.TimeoutExpired:
            return ActionResult(
                request.key,
                ActionOutcome.UNKNOWN,
                error_code="visible_control_unavailable",
            )
        return self._helper_result(request, result)

    @staticmethod
    def _consent_argument(consent: ControlEvidence | None) -> list[str]:
        if (
            consent is None
            or consent.source != "accessibility"
            or consent.anchor is None
        ):
            return []
        return ["consent=" + json.dumps([*consent.anchor, consent.checked])]

    @staticmethod
    def _helper_result(
        request: ActionRequest, result: subprocess.CompletedProcess[str]
    ) -> ActionResult:
        if result.stdout.startswith("BACKEND_UNAVAILABLE:"):
            return ActionResult(
                request.key,
                ActionOutcome.FAILED,
                error_code="backend:" + result.stdout.strip().partition(":")[2],
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
            match = re.fullmatch(r"TARGET_CHANGED:([^\r\n]+)\r?\n?", result.stdout)
            detail = match.group(1) if match is not None else ""
            suffix = (
                detail
                if (
                    detail in _TARGET_CHANGED_CODES
                    or _IMAGE_SCALE_CODE.fullmatch(detail)
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
        elif result.returncode == 0 and result.stdout.strip() in {
            "STATE_ALREADY_SET",
            "STATE_CONFIRMED",
            "NAVIGATION_CONFIRMED",
        }:
            outcome, reason = ActionOutcome.CONFIRMED, None
        elif result.returncode == 0 and result.stdout.strip() in {
            "CLICK_DISPATCHED",
            "ACTION_DISPATCHED",
        }:
            outcome, reason = ActionOutcome.DISPATCHED_UNVERIFIED, None
        elif result.stdout.strip() == "ACTION_UNCONFIRMED":
            outcome, reason = ActionOutcome.UNKNOWN, "visible_control_unconfirmed"
        else:
            outcome, reason = ActionOutcome.UNKNOWN, "visible_control_unavailable"
        return ActionResult(request.key, outcome, error_code=reason)
