"""System-Python compatible lifetime and permission checks for input helpers."""

from __future__ import annotations

import os
import select
import signal
from pathlib import Path
from time import monotonic
from typing import Any

from kyrin.app.permission_token import read_opaque_token
from kyrin.operations import Operation, OperationStopped, activate, remaining


class HelperLifetime:
    """One portal connection, bounded calls and a generation check per input.

    The opaque restore token also acts as a local permission epoch: unlink or
    replacement invalidates this helper, including during portal startup. Only
    this helper's authorized token rotation advances its expected value.
    """

    def __init__(self, connection: Any, token_path: Path, token: str | None) -> None:
        self.connection = connection
        self.token_path = token_path
        self.token = token
        self.channel_fd: int | None = None
        raw_fd = os.environ.get("KYRIN_OPERATION_FD")
        if raw_fd is not None:
            self.channel_fd = int(raw_fd)
        self.operation = Operation(
            float(os.environ.get("KYRIN_OPERATION_DEADLINE", str(monotonic() + 65)))
        )
        self._activation = activate(self.operation)
        self._activation.__enter__()
        self._previous_signal = signal.signal(signal.SIGTERM, self._terminated)

    def _terminated(self, _signal: int, _frame: Any) -> None:
        self.operation.cancel()
        raise OperationStopped("helper owner cancelled")

    def check(self, *, input_event: bool = False) -> None:
        self.operation.remaining()
        if read_opaque_token(self.token_path) != self.token:
            raise OperationStopped("input permission epoch changed")
        if input_event and self.channel_fd is not None:
            try:
                os.write(self.channel_fd, b"?")
                ready = select.select(
                    [self.channel_fd], [], [], self.operation.remaining()
                )
                if not ready[0] or os.read(self.channel_fd, 1) != b"Y":
                    raise OperationStopped("input owner disappeared")
            except OSError as error:
                raise OperationStopped("input owner unavailable") from error
            self.operation.remaining()
            if read_opaque_token(self.token_path) != self.token:
                raise OperationStopped("input permission epoch changed")

    def rotate(self, token: str) -> None:
        from kyrin.app.permission_token import save_opaque_token

        self.check()
        save_opaque_token(self.token_path, token)
        self.token = token
        self.check()

    def call_sync(self, *args: Any) -> Any:
        # Closing resources is permitted after expiry/revocation. It has its
        # own small cleanup allowance and cannot send any keyboard/pointer input.
        values = list(args)
        if values[3] == "Close":
            values[7] = min(values[7], 200)
        else:
            self.check(input_event=values[3].startswith("Notify"))
            values[7] = max(1, min(values[7], int(remaining(values[7] / 1000) * 1000)))
        return self.connection.call_sync(*values)

    def __getattr__(self, name: str) -> Any:
        return getattr(self.connection, name)

    def close(self) -> None:
        signal.signal(signal.SIGTERM, self._previous_signal)
        if self.channel_fd is not None:
            os.close(self.channel_fd)
        self._activation.__exit__(None, None, None)
