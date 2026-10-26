"""Application-owned input transport; no portal startup on the command path.

Only an inherited socketpair connects the application to its system-Python
owner. No listening socket, discoverable endpoint, token or desktop identifier
can reconnect another process. The existing DesktopInputBroker admits actions;
this lock protects the wire and never admits a second input owner.
"""

from __future__ import annotations

import atexit
import json
import select
import socket
import subprocess
from collections.abc import Sequence
from pathlib import Path
from threading import Lock, RLock
from time import monotonic
from typing import Any
from uuid import uuid4

from kyrin.app.permission_token import permission_token_path, read_opaque_token
from kyrin.app.permissions import PermissionPolicy
from kyrin.operations import OperationStopped, budget, run_process

HELPERS = {
    "desktop_scroll_helper.py": ("desktop_scroll", 2),
    "desktop_control_helper.py": ("desktop_control", 2),
    "telegram_portal_helper.py": ("telegram_chat", 3),
}
BUILD = "desktop-input-owner-2026-10-25-l03"
MAX_MESSAGE = 1024 * 1024


class Wire:
    def __init__(self, channel: socket.socket) -> None:
        self.channel = channel
        self.pending = b""

    def send(self, message: dict[str, Any]) -> None:
        payload = json.dumps(message, ensure_ascii=True).encode() + b"\n"
        if len(payload) > MAX_MESSAGE:
            raise ValueError("input message too large")
        self.channel.sendall(payload)

    def receive(self, timeout: float) -> dict[str, Any] | None:
        if b"\n" not in self.pending:
            if not select.select([self.channel], [], [], timeout)[0]:
                return None
            data = self.channel.recv(65536)
            if not data:
                raise ConnectionError("input owner disconnected")
            self.pending += data
            if len(self.pending) > MAX_MESSAGE:
                raise ValueError("input response too large")
        if b"\n" not in self.pending:
            return None
        line, self.pending = self.pending.split(b"\n", 1)
        message = json.loads(line)
        if not isinstance(message, dict):
            raise ValueError("invalid input response")
        return message


class InputSessionService:
    def __init__(self) -> None:
        self._wire_lock = Lock()
        self._state_lock = RLock()
        self._process: subprocess.Popen[bytes] | None = None
        self._wire: Wire | None = None
        self._generation = 0
        self._policy: PermissionPolicy | None = None
        self._state = "unprepared"

    def configure(self, policy: PermissionPolicy) -> None:
        with self._state_lock:
            previous = self._policy
            self._policy = policy
            # Publish policy and invalidate the old owner as one transition.
            if previous is not None and any(
                self._selected(previous, cap) and not self._selected(policy, cap)
                for cap, _devices in HELPERS.values()
            ):
                self.disconnect(forget=True)
            elif previous is not None and (
                previous.settings.action_execution_enabled
                and not policy.settings.action_execution_enabled
            ):
                self.disconnect()

    @staticmethod
    def _selected(policy: PermissionPolicy, capability: str) -> bool:
        if capability == "telegram_chat":
            return policy.has_grant(capability, "telegram") and (
                policy.settings.remember_telegram_pointer
                or policy.settings.trust_all_capabilities
            )
        return policy.has_grant(capability)

    def _allowed(self, capability: str, *, setup: bool) -> bool:
        policy = self._policy
        return (
            policy is not None
            and self._selected(policy, capability)
            and (setup or policy.settings.action_execution_enabled)
        )

    def startup_capability(self) -> str | None:
        """Choose a saved grant for one startup restoration attempt."""
        with self._state_lock:
            policy = self._policy
            if (
                policy is None
                or not policy.settings.action_execution_enabled
                or self._wire is not None
                or read_opaque_token(permission_token_path("desktop-input")) is None
            ):
                return None
            return next(
                (
                    capability
                    for capability, _devices in sorted(
                        HELPERS.values(), key=lambda item: item[1], reverse=True
                    )
                    if self._selected(policy, capability)
                ),
                None,
            )

    def disconnect(self, *, forget: bool = False) -> None:
        with self._state_lock:
            self._generation += 1
            process, self._process = self._process, None
            wire, self._wire = self._wire, None
            self._state = "disconnected"
            if wire is not None:
                wire.channel.close()
            if process is not None:
                try:
                    process.terminate()
                except ProcessLookupError:
                    pass
                try:
                    process.wait(timeout=0.3)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
            if forget:
                permission_token_path("desktop-input").unlink(missing_ok=True)

    def _start(self) -> None:
        parent, child = socket.socketpair()
        parent.settimeout(0.2)
        try:
            process = subprocess.Popen(
                [
                    "/usr/bin/python3",
                    str(Path(__file__).with_name("input_session_owner.py")),
                    str(child.fileno()),
                ],
                pass_fds=(child.fileno(),),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
        except BaseException:
            parent.close()
            raise
        finally:
            child.close()
        self._process = process
        self._wire = Wire(parent)

    def _exchange(
        self,
        command: str,
        *,
        capability: str = "",
        timeout: float = 2,
        restore: bool = False,
        **payload: Any,
    ) -> dict[str, Any]:
        with self._state_lock:
            admitted_generation = self._generation
        with budget(timeout) as operation:
            while not self._wire_lock.acquire(timeout=min(0.02, operation.remaining())):
                operation.remaining()
            try:
                operation.remaining()
                setup = command == "prepare"
                with self._state_lock:
                    if admitted_generation != self._generation:
                        raise OperationStopped("input request predates disconnect")
                    if capability and not self._allowed(
                        capability, setup=setup and not restore
                    ):
                        return {
                            "state": "unprepared",
                            "stdout": "CONTROL_SETUP_REQUIRED\n",
                            "code": 3,
                        }
                    if setup:
                        if restore and read_opaque_token(
                            permission_token_path("desktop-input")
                        ) is None:
                            return {"state": self._state, "devices": 0}
                        # One consent covers all currently selected input needs.
                        # Scroll/click share pointer; Telegram also needs keyboard.
                        policy = self._policy
                        assert policy is not None
                        requested_devices = 0
                        for selected, required in HELPERS.values():
                            if self._selected(policy, selected):
                                requested_devices |= required
                        payload["devices"] = requested_devices
                    if self._wire is None:
                        if not setup:
                            return {
                                "state": self._state,
                                "devices": 0,
                                "stdout": "CONTROL_SETUP_REQUIRED\n",
                                "code": 3,
                            }
                        self._start()
                    wire = self._wire
                    generation = self._generation
                    if setup:
                        self._state = "preparing"
                assert wire is not None
                request_id = uuid4().hex
                wire.send(
                    {
                        "id": request_id,
                        "command": command,
                        "build": BUILD,
                        "protocol_version": 1,
                        "deadline": monotonic() + operation.remaining(),
                        **payload,
                    }
                )
                while True:
                    operation.remaining()
                    with self._state_lock:
                        if generation != self._generation:
                            raise OperationStopped("input session revoked")
                        if capability and not self._allowed(
                            capability, setup=setup and not restore
                        ):
                            raise OperationStopped("input permission revoked")
                    response = wire.receive(min(0.02, operation.remaining()))
                    if response is None:
                        continue
                    if response.get("id") != request_id:
                        raise ConnectionError("unmatched input response")
                    if response.get("checkpoint"):
                        # Acknowledgement commits at most this one input event.
                        # Revocation is ordered against that boundary.
                        with self._state_lock:
                            operation.remaining()
                            if generation != self._generation or (
                                capability
                                and not self._allowed(
                                    capability, setup=setup and not restore
                                )
                            ):
                                raise OperationStopped("input authorization revoked")
                            wire.send({"id": request_id, "authorized": True})
                        continue
                    operation.remaining()
                    capabilities = response.get("capabilities")
                    state, devices = response.get("state"), response.get("devices")
                    if (
                        response.get("build") != BUILD
                        or type(response.get("protocol_version")) is not int
                        or response["protocol_version"] != 1
                        or not isinstance(capabilities, list)
                        or "shared-input-session-v1" not in capabilities
                        or not isinstance(state, str)
                        or state
                        not in {
                            "unprepared",
                            "preparing",
                            "ready",
                            "disconnected",
                            "unsupported",
                            "interaction_required",
                        }
                        or type(devices) is not int
                        or not 0 <= devices <= 3
                        or (state == "ready" and devices == 0)
                        or type(response.get("starts")) is not int
                        or response["starts"] < 0
                        or type(response.get("persistent")) is not bool
                        or type(response.get("code")) is not int
                        or not isinstance(response.get("stdout"), str)
                        or not isinstance(response.get("stderr"), str)
                    ):
                        raise ConnectionError("incompatible input owner response")
                    with self._state_lock:
                        if generation != self._generation:
                            raise OperationStopped("late input setup")
                        self._state = str(response.get("state", "disconnected"))
                    return response
            except OSError, ValueError, OperationStopped:
                # Outcome may be unknown; never retry this request or restore
                # a session automatically. Closing the connection drops input.
                with self._state_lock:
                    if admitted_generation == self._generation:
                        self.disconnect()
                raise
            finally:
                self._wire_lock.release()

    def prepare(self, capability: str, *, restore: bool = False) -> dict[str, Any]:
        if capability not in {c for c, _devices in HELPERS.values()}:
            raise ValueError("unknown input capability")
        return self._exchange(
            "prepare", capability=capability, restore=restore, timeout=45
        )

    def status(self) -> dict[str, Any]:
        if self._wire_lock.locked():
            return {
                "state": "busy" if self._state == "ready" else self._state,
                "devices": 0,
            }
        try:
            return self._exchange("status")
        except OSError, ValueError, OperationStopped:
            return {"state": "disconnected", "devices": 0}

    def run(
        self, args: Sequence[str], *, timeout: float
    ) -> subprocess.CompletedProcess[str]:
        capability, devices = HELPERS[Path(args[1]).name]
        if (
            Path(args[1]).name == "desktop_scroll_helper.py"
            and args[-1] == "telegram-control"
        ):
            capability = "telegram_chat"
        reply = self._exchange(
            "execute",
            capability=capability,
            timeout=timeout,
            helper=Path(args[1]).name,
            args=list(args[2:]),
            devices=devices,
        )
        return subprocess.CompletedProcess(
            args,
            int(reply.get("code", 3)),
            str(reply.get("stdout", "CONTROL_SETUP_REQUIRED\n")),
            str(reply.get("stderr", "")),
        )


INPUT_SESSIONS = InputSessionService()
atexit.register(INPUT_SESSIONS.disconnect)


def run_input_helper(
    args: Sequence[str], **kwargs: Any
) -> subprocess.CompletedProcess[Any]:
    if kwargs.get("helper") and len(args) > 1 and Path(args[1]).name in HELPERS:
        return INPUT_SESSIONS.run(args, timeout=float(kwargs["timeout"]))
    return run_process(args, **kwargs)
