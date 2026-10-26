"""A local SSIP connection with cancellation scoped to its own speech only."""

import os
import socket
from collections.abc import Callable
from pathlib import Path
from threading import Event
from time import monotonic


class LocalSpeechConnection:
    """One message per connection; only the speech worker performs socket I/O."""

    def __init__(self, timeout_s: float) -> None:
        address = os.environ.get("SPEECHD_ADDRESS")
        if address is not None and not address.startswith("unix:"):
            raise OSError("Only local Unix Speech Dispatcher connections are supported")
        path = (address[5:] if address else os.environ.get("SPEECHD_SOCKET")) or str(
            Path(os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}"))
            / "speech-dispatcher/speechd.sock"
        )
        self._socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._socket.settimeout(0.05)
        try:
            self._socket.connect(path)
        except OSError:
            self._socket.close()
            raise
        self._deadline = monotonic() + timeout_s
        self._buffer = bytearray()
        self._playing: Callable[[bool], None] = lambda value: None
        self._finished = False
        self.output_uncertain = False

    def close(self) -> None:
        self._socket.close()

    def _reply(self, *, poll: bool = False) -> int | None:
        while True:
            if monotonic() >= self._deadline:
                raise TimeoutError("Speech Dispatcher deadline expired")
            while b"\r\n" not in self._buffer:
                try:
                    data = self._socket.recv(4096)
                except TimeoutError:
                    if poll:
                        return None
                    if monotonic() >= self._deadline:
                        raise
                    continue
                if not data:
                    raise OSError("Speech Dispatcher disconnected")
                self._buffer.extend(data)
                if len(self._buffer) > 65536:
                    raise OSError("Oversized Speech Dispatcher reply")
            line, _, rest = self._buffer.partition(b"\r\n")
            self._buffer = bytearray(rest)
            if (
                len(line) < 4
                or not line[:3].isdigit()
                or bytes(line[3:4]) not in (b"-", b" ")
            ):
                raise OSError("Invalid Speech Dispatcher reply")
            if line[3:4] == b"-":
                continue
            code = int(line[:3])
            if code == 701:
                self._playing(True)
            elif code in (702, 703):
                self._playing(False)
                self._finished = True
                self.output_uncertain = False
            if code // 100 != 7:
                return code
            if poll:
                return None

    def _command(self, command: str) -> None:
        self._socket.sendall(command.encode("utf-8") + b"\r\n")
        code = self._reply()
        if code is None or code // 100 != 2:
            raise OSError("Speech Dispatcher rejected a command")

    def speak(
        self,
        text: str,
        language: str,
        rate: int,
        voice: str,
        cancelled: Event,
        is_current: Callable[[], bool],
        playing: Callable[[bool], None],
    ) -> None:
        self._playing = playing
        for command in (
            "SET SELF CLIENT_NAME kyrin:KYRIN:responses",
            "SET SELF OUTPUT_MODULE espeak-ng",
            "SET SELF PRIORITY TEXT",
            f"SET SELF LANGUAGE {language}",
            f"SET SELF RATE {rate}",
            "SET SELF NOTIFICATION BEGIN on",
            "SET SELF NOTIFICATION END on",
            "SET SELF NOTIFICATION CANCEL on",
        ):
            if cancelled.is_set() or not is_current():
                return
            self._command(command)
        if voice != "default":
            self._command(f"SET SELF VOICE {voice}")
        if cancelled.is_set() or not is_current():
            return
        self._command("SPEAK")
        # Normalize newlines and dot-stuff data, including the first line.
        lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
        data = "\r\n".join(
            "." + line if line.startswith(".") else line for line in lines
        )
        self.output_uncertain = True
        try:
            self._socket.sendall(data.encode("utf-8") + b"\r\n.\r\n")
            code = self._reply()
            if code is None or code // 100 != 2:
                raise OSError("Speech Dispatcher rejected speech data")
            while not self._finished:
                if cancelled.is_set() or not is_current():
                    break
                self._reply(poll=True)
        finally:
            if not self._finished:
                # This connection owns one message. Never send CANCEL ALL.
                self._deadline = monotonic() + 0.5
                self._command("CANCEL SELF")
                self.output_uncertain = False
                playing(False)
