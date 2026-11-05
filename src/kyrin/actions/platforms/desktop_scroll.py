"""One bounded scroll in the focused, explicitly permitted desktop app."""

import subprocess
from collections.abc import Callable, Mapping
from pathlib import Path
from time import monotonic

from kyrin.actions.cancellation import execute_with_budget
from kyrin.actions.executor import ActionExecutor
from kyrin.actions.models import ActionOutcome, ActionRequest, ActionResult
from kyrin.actions.platforms.input_session import run_input_helper as run_process
from kyrin.backend_protocol import BackendUnavailable
from kyrin.commands.models import CommandKind
from kyrin.desktop.platforms.gnome import read_active_window_token

SCROLL_HELPER = Path(__file__).with_name("desktop_scroll_helper.py")
WindowIdentityReader = Callable[[], tuple[str, int] | None]
_SCROLL_KINDS = (CommandKind.SCROLL_UP, CommandKind.SCROLL_DOWN)
_MAX_SCROLL_SECONDS = 45.0


class DesktopScrollExecutor:
    def __init__(
        self,
        delegate: ActionExecutor,
        *,
        desktop_ids: Mapping[str, str],
        identity_reader: WindowIdentityReader,
        allow_any_focused_app: bool = False,
        helper_path: Path = SCROLL_HELPER,
        system_python: str = "/usr/bin/python3",
        token_reader: Callable[[], str | None] | None = None,
    ) -> None:
        self._delegate = delegate
        self._desktop_ids = dict(desktop_ids)
        self._identity_reader = identity_reader
        self._token_reader = token_reader or read_active_window_token
        self._allow_any_focused_app = allow_any_focused_app
        self._helper_path = helper_path
        self._system_python = system_python

    def execute(self, request: ActionRequest) -> ActionResult:
        observation = request.intent.scroll_observation
        if request.intent.kind in _SCROLL_KINDS and (
            observation is None or monotonic() >= observation.deadline
        ):
            # Missing or expired evidence never reaches input admission.
            return self._window_changed(request)
        timeout = (
            min(_MAX_SCROLL_SECONDS, observation.deadline - monotonic())
            if observation is not None
            else _MAX_SCROLL_SECONDS
        )
        return execute_with_budget(
            request, lambda: self._execute(request), timeout_s=timeout
        )

    @staticmethod
    def _window_changed(request: ActionRequest) -> ActionResult:
        return ActionResult(
            request.key, ActionOutcome.FAILED, error_code="scroll_focus_changed"
        )

    def _execute(self, request: ActionRequest) -> ActionResult:
        kind = request.intent.kind
        if kind not in _SCROLL_KINDS:
            return self._delegate.execute(request)
        desktop_id = (
            request.intent.target
            if self._allow_any_focused_app
            else self._desktop_ids.get(request.intent.target)
        )
        observation = request.intent.scroll_observation
        identity = self._identity_reader()
        # The request is bound to the window observed when it was spoken. A
        # same-app or same-process replacement window is a different target.
        if (
            desktop_id is None
            or observation is None
            or observation.app_id != desktop_id
            or identity is None
            or identity != observation.identity
            or not observation.current(self._token_reader(), monotonic())
        ):
            return self._window_changed(request)
        remaining = observation.deadline - monotonic()
        if remaining <= 0:
            return self._window_changed(request)
        is_telegram = "telegram" in identity[0].casefold()
        if request.intent.scroll_area is not None and not is_telegram:
            return ActionResult(
                request.key,
                ActionOutcome.FAILED,
                error_code="unsupported_scroll_area",
            )
        area = (
            "right"
            if request.intent.scroll_area == "chat"
            else "left"
            if request.intent.scroll_area == "list" or is_telegram
            else "center"
        )
        try:
            completed = run_process(
                [
                    self._system_python,
                    str(self._helper_path),
                    identity[0],
                    str(identity[1]),
                    "up" if kind is CommandKind.SCROLL_UP else "down",
                    str(request.intent.scroll_steps or 3),
                    area,
                    observation.to_json(),
                    "desktop-scroll",
                ],
                helper=True,
                helper_capabilities={"desktop_scroll-v1"},
                capture_output=True,
                text=True,
                timeout=min(_MAX_SCROLL_SECONDS, remaining),
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
                request.key, ActionOutcome.UNKNOWN, error_code="scroll_unavailable"
            )
        if completed.stdout.startswith("BACKEND_UNAVAILABLE:"):
            return ActionResult(
                request.key,
                ActionOutcome.FAILED,
                error_code="backend:" + completed.stdout.strip().partition(":")[2],
            )
        if "CONTROL_SETUP_REQUIRED" in completed.stdout:
            return ActionResult(
                request.key,
                ActionOutcome.FAILED,
                error_code="scroll_control_setup_required",
            )
        if completed.stdout.strip() == "FOCUS_CHANGED":
            # The helper prints this only before sending any input event.
            return self._window_changed(request)
        if completed.returncode == 0 and "SCROLL_DISPATCHED" in completed.stdout:
            return ActionResult(
                request.key,
                ActionOutcome.DISPATCHED_UNVERIFIED,
            )
        return ActionResult(
            request.key, ActionOutcome.UNKNOWN, error_code="scroll_unavailable"
        )
