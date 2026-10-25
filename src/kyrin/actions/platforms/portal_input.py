"""Live portal session state, independent of microphone and restore tokens."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any, Protocol

from kyrin.app.permission_token import (
    consume_opaque_token,
    read_opaque_token,
    save_opaque_token,
)


class PortalBackend(Protocol):
    connection: Any
    version: int
    available: int

    def request(self, method: str, args: tuple[Any, ...]) -> dict[str, Any] | None: ...
    def watch(self, session: str) -> None: ...
    def alive(self, session: str) -> bool: ...
    def close(self, session: str) -> None: ...
    def options(self, devices: int, token: str | None) -> dict[str, Any]: ...


class PortalInputSession:
    def __init__(self, backend: PortalBackend, token_path: Path) -> None:
        self.backend = backend
        self.token_path = token_path
        self.session: str | None = None
        self.devices = 0
        self.starts = 0
        self.state = "unprepared"
        self.persistent = False

    def status(self) -> dict[str, Any]:
        if self.session is not None and not self.backend.alive(self.session):
            self.close()
        return {
            "state": self.state,
            "devices": self.devices,
            "persistent": self.persistent,
            "starts": self.starts,
        }

    def close(self) -> None:
        session, self.session = self.session, None
        self.devices = 0
        self.state = "disconnected"
        if session is not None:
            self.backend.close(session)

    def prepare(self, devices: int, check: Callable[[], None]) -> dict[str, Any]:
        check()
        self.status()
        if self.session is not None and self.devices & devices == devices:
            return self.status()
        devices |= self.devices  # Extension only from explicit settings setup.
        self.close()
        if self.backend.version < 1 or self.backend.available & devices != devices:
            self.state = "unsupported"
            return self.status()
        self.state = "preparing"
        created = self.backend.request("CreateSession", ({},))
        if created is None:
            self.state = "interaction_required"
            return self.status()
        self.session = str(created["session_handle"])
        self.backend.watch(self.session)
        try:
            check()
            # Claim before SelectDevices: tokens are single-use even if Start
            # fails or the caller is killed while the portal consumes the token.
            token = consume_opaque_token(self.token_path)
            options = self.backend.options(devices, token)
            if self.backend.request("SelectDevices", (self.session, options)) is None:
                self.close()
                self.state = "interaction_required"
                return self.status()
            check()
            started = self.backend.request("Start", (self.session, "", {}))
            check()
            if started is None or int(started.get("devices", 0)) & devices != devices:
                self.close()
                self.state = "interaction_required"
                return self.status()
            self.devices = int(started["devices"]) & devices
            self.starts += 1
            replacement = started.get("restore_token")
            self.persistent = False
            if isinstance(replacement, str):
                try:
                    save_opaque_token(self.token_path, replacement)
                    self.persistent = True
                except OSError, ValueError:
                    # Current live consent still works without durable storage.
                    pass
            check()
            self.state = "ready"
            return self.status()
        except BaseException:
            self.close()
            raise

    def acquire(self, devices: int) -> tuple[Any, str, Path, str | None] | None:
        self.status()
        if self.session is None or self.devices & devices != devices:
            return None
        return (
            self.backend.connection,
            self.session,
            self.token_path,
            read_opaque_token(self.token_path),
        )
