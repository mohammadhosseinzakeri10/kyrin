"""Create a tab through an exact focused window, never Ptyxis MRU routing."""

import json
import subprocess
from collections.abc import Callable
from dataclasses import replace
from time import monotonic, sleep
from uuid import uuid4

from kyrin.actions.cancellation import execute_with_budget
from kyrin.actions.executor import ActionExecutor
from kyrin.actions.models import ActionOutcome, ActionRequest, ActionResult
from kyrin.app.permissions import PermissionPolicy
from kyrin.backend_protocol import probe_gnome
from kyrin.commands.models import CommandIntent, CommandKind
from kyrin.desktop.window_observation import WindowObservation
from kyrin.operations import check_operation, run_process


class PtyxisTabExecutor:
    """One-use picker continuation plus existing identity-bound AT-SPI controls.

    The outer input broker owns selection and both controls as one operation.
    Selection is a new explicit command, with a fresh ten-second execution
    observation. It cannot renew the thirty-second displayed-choice lifetime.
    """

    def __init__(
        self,
        delegate: ActionExecutor,
        controls: ActionExecutor,
        *,
        app_id: str,
        desktop_id: str,
        permissions: PermissionPolicy,
        identity_reader: Callable[[], tuple[str, int] | None],
        token_reader: Callable[[], str | None],
    ) -> None:
        if desktop_id != "org.gnome.Ptyxis.desktop":
            raise ValueError("targeted tabs require the reviewed Ptyxis binding")
        self._delegate = delegate
        self._controls = controls
        self._app_id = app_id
        self._desktop_id = desktop_id
        self._permissions = permissions
        self._identity = identity_reader
        self._token = token_reader
        self._selection: tuple[str, float] | None = None

    def execute(self, request: ActionRequest) -> ActionResult:
        return execute_with_budget(
            request, lambda: self._execute(request), timeout_s=10
        )

    def _call(self, method: str, signature: str, *args: str) -> dict[str, object]:
        status = probe_gnome("ActiveApp", {method}, run=run_process)
        if not status.ready:
            return {"status": "backend:" + status.reason}
        try:
            completed = run_process(
                [
                    "busctl",
                    "--user",
                    "--json=short",
                    "call",
                    "org.gnome.Shell",
                    "/org/kyrin/ActiveApp",
                    "org.kyrin.ActiveApp",
                    method,
                    signature,
                    *args,
                ],
                capture_output=True,
                text=True,
                check=False,
                timeout=2,
            )
            envelope = json.loads(completed.stdout)
            if completed.returncode != 0 or envelope.get("type") != "s":
                return {"status": "window_unverified"}
            reply = json.loads(envelope["data"][0])
            return reply if isinstance(reply, dict) else {"status": "window_unverified"}
        except (
            OSError,
            subprocess.TimeoutExpired,
            ValueError,
            KeyError,
            IndexError,
            TypeError,
            AttributeError,
        ):
            return {"status": "window_unverified"}

    def _execute(self, request: ActionRequest) -> ActionResult:
        intent = request.intent

        def failure(reason: str) -> ActionResult:
            return ActionResult(request.key, ActionOutcome.FAILED, error_code=reason)

        showing = (
            intent.kind is CommandKind.SHOW_APP_WINDOWS
            and intent.tab_selection_id is not None
        )
        if not showing and intent.kind is not CommandKind.NEW_APP_TAB:
            self._selection = None
            return self._delegate.execute(request)
        if intent.target != self._app_id:
            return failure("app_not_configured")
        if not self._permissions.allows_intent(
            CommandIntent(CommandKind.NEW_APP_TAB, self._app_id)
        ) or not self._permissions.allows("desktop_control"):
            self._selection = None
            return failure("action_not_allowed")
        if showing:
            self._selection = None
            if not self._permissions.allows_intent(intent):
                return failure("action_not_allowed")
            started = monotonic()
            assert intent.tab_selection_id is not None
            reply = self._call(
                "ShowAppWindowsForTab", "ss", self._desktop_id, intent.tab_selection_id
            )
            count = reply.get("count")
            if (
                reply.get("status") != "requested"
                or reply.get("generation") != intent.tab_selection_id
                or type(count) is not int
                or not 1 <= count <= 32
            ):
                reason = reply.get("status")
                return failure(
                    reason
                    if isinstance(reason, str) and reason != "requested"
                    else "window_unverified"
                )
            self._selection = intent.tab_selection_id, started + 30.0
            return ActionResult(request.key, ActionOutcome.LAUNCH_ACCEPTED)

        observation = intent.tab_observation
        if intent.tab_selection_id is not None:
            selection, self._selection = self._selection, None
            if (
                selection is None
                or selection[0] != intent.tab_selection_id
                or monotonic() >= selection[1]
                or not self._permissions.allows("window_control", self._app_id)
            ):
                return failure("window_state_changed")
            started = monotonic()
            reply = self._call(
                "ActivateAppWindowForTab",
                "ssu",
                self._desktop_id,
                intent.tab_selection_id,
                str(intent.window_index),
            )
            pid, token = reply.get("process_id"), reply.get("window_token")
            if (
                reply.get("status") != "requested"
                or reply.get("app_id") != self._desktop_id
                or reply.get("generation") != intent.tab_selection_id
                or type(pid) is not int
                or pid <= 0
                or not isinstance(token, str)
                or not token
            ):
                return failure("window_state_changed")
            if monotonic() >= selection[1]:
                return failure("window_state_changed")
            observation = WindowObservation(
                self._desktop_id,
                pid,
                token,
                uuid4().hex,
                started,
                min(started + 10.0, selection[1]),
            )
            # Activation is asynchronous. Only the returned exact token may
            # complete it; another window from the same PID is never sufficient.
            while self._token() != token or self._identity() != observation.identity:
                check_operation()
                if monotonic() >= min(started + 1.0, observation.deadline):
                    return failure("window_state_changed")
                sleep(0.025)
        else:
            self._selection = None
        if (
            observation is None
            or observation.app_id != self._desktop_id
            or not observation.current(self._token(), monotonic())
            or self._identity() != observation.identity
        ):
            return failure("window_state_changed")

        check_operation()
        # The fixed semantic operation remains NEW_APP_TAB. The helper binds the
        # live unnamed menu Action to the owner's configured tab shortcut; it
        # never disguises an unnamed item as a verified visible text label.
        return self._controls.execute(
            replace(
                request,
                intent=replace(
                    intent,
                    window_index=None,
                    tab_selection_id=None,
                    tab_observation=observation,
                ),
            )
        )
