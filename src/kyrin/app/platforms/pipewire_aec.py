"""Own a temporary PipeWire echo-cancellation source for a listening session."""

import json
import os
import re
import shutil
import signal
import subprocess
import time
from pathlib import Path
from uuid import uuid4

from kyrin.audio.pipewire_echo_input import PipeWireEchoInput


class PipeWireEchoCancellation:
    """Use PipeWire's WebRTC AEC against the default microphone and sink."""

    def __init__(self, *, ready_timeout_s: float = 2.0) -> None:
        self._ready_timeout_s = ready_timeout_s
        self._process: subprocess.Popen[str] | None = None
        self._record: str | None = None
        self._source_name = f"kyrin-echo-{os.getpid()}-{uuid4().hex[:8]}"

    def start(self) -> bool:
        cli = shutil.which("pw-cli")
        dump = shutil.which("pw-dump")
        record = shutil.which("pw-record")
        if not cli or not dump or not record:
            return False
        self._cleanup_stale_sources(dump)
        try:
            process = subprocess.Popen(
                [cli], stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL, text=True,
            )
            self._process = process
            self._record = record
            assert process.stdin is not None
            process.stdin.write(
                "load-module libpipewire-module-echo-cancel "
                "{ monitor.mode = true "
                f'source.props = {{ node.name = "{self._source_name}" '
                'node.description = "KYRIN echo-cancelled microphone" } }\n'
            )
            process.stdin.flush()
            deadline = time.monotonic() + self._ready_timeout_s
            while time.monotonic() < deadline and process.poll() is None:
                if self._source_exists(dump):
                    return True
                time.sleep(0.05)
        except (OSError, ValueError, subprocess.SubprocessError):
            pass
        self.close()
        return False

    def input(self) -> PipeWireEchoInput:
        if self._process is None or self._process.poll() is not None:
            raise RuntimeError("PipeWire echo cancellation is unavailable")
        assert self._record is not None
        return PipeWireEchoInput(self._source_name, self._record)

    def close(self) -> None:
        process = self._process
        self._process = None
        if process is None:
            return
        try:
            if process.poll() is None and process.stdin is not None:
                process.stdin.write("quit\n")
                process.stdin.flush()
                process.stdin.close()
            process.wait(timeout=2)
        except (OSError, ValueError, subprocess.TimeoutExpired):
            process.kill()
            process.wait(timeout=2)

    def _source_exists(self, executable: str) -> bool:
        result = subprocess.run(
            [executable], capture_output=True, text=True, timeout=1,
            check=False,
        )
        if result.returncode:
            return False
        graph = json.loads(result.stdout)
        return any(
            item.get("info", {}).get("props", {}).get("node.name")
            == self._source_name
            for item in graph
        )

    @staticmethod
    def _cleanup_stale_sources(executable: str) -> None:
        """Remove only orphaned sources created by older KYRIN processes."""
        try:
            result = subprocess.run(
                [executable], capture_output=True, text=True, timeout=1,
                check=False,
            )
            if result.returncode:
                return
            graph = json.loads(result.stdout)
        except (OSError, ValueError, subprocess.TimeoutExpired):
            return
        clients = {item.get("id"): item for item in graph}
        for item in graph:
            props = item.get("info", {}).get("props", {})
            name = props.get("node.name", "")
            match = re.fullmatch(r"kyrin-echo-(\d+)-[0-9a-f]{8}", name)
            if match is None:
                continue
            if PipeWireEchoCancellation._is_live_kyrin(int(match[1])):
                continue
            try:
                client_id = int(props.get("client.id", 0))
            except (TypeError, ValueError):
                client_id = 0
            client = clients.get(client_id, {})
            client_props = client.get("info", {}).get("props", {})
            try:
                module_pid = int(client_props.get("pipewire.sec.pid", 0))
            except (TypeError, ValueError):
                module_pid = 0
            PipeWireEchoCancellation._terminate_owned_process(
                module_pid, b"/pw-cli\0"
            )
            for process in Path("/proc").iterdir():
                if not process.name.isdigit():
                    continue
                try:
                    command = (process / "cmdline").read_bytes()
                except OSError:
                    continue
                if (
                    b"/pw-record\0--target\0" + name.encode() + b"\0"
                ) in command:
                    PipeWireEchoCancellation._terminate_owned_process(
                        int(process.name), b"/pw-record\0"
                    )

    @staticmethod
    def _is_live_kyrin(pid: int) -> bool:
        try:
            command = (Path("/proc") / str(pid) / "cmdline").read_bytes()
        except OSError:
            return False
        return b"/kyrin-desktop\0" in command

    @staticmethod
    def _terminate_owned_process(pid: int, executable_suffix: bytes) -> None:
        if pid <= 0 or pid == os.getpid():
            return
        path = Path("/proc") / str(pid)
        try:
            if path.stat().st_uid != os.getuid():
                return
            command = (path / "cmdline").read_bytes()
            executable = command.split(b"\0", 1)[0]
            if not executable.endswith(executable_suffix.rstrip(b"\0")):
                return
            os.kill(pid, signal.SIGTERM)
        except (OSError, ProcessLookupError):
            return
