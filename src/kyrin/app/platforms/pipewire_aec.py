"""Own a temporary PipeWire echo-cancellation source for a listening session."""

import json
import os
import re
import shutil
import signal
import subprocess
import time
from pathlib import Path
from typing import Any
from uuid import uuid4

from kyrin.audio.pipewire_echo_input import PipeWireEchoInput


class PipeWireEchoCancellation:
    """Use PipeWire's WebRTC AEC against a resolved microphone and default sink."""

    def __init__(self, *, ready_timeout_s: float = 2.0) -> None:
        self._ready_timeout_s = ready_timeout_s
        self._process: subprocess.Popen[str] | None = None
        self._record: str | None = None
        self._target: str | None = None
        self._source_name = f"kyrin-echo-{os.getpid()}-{uuid4().hex[:8]}"

    def start(self, microphone_key: str | None = None) -> bool:
        cli = shutil.which("pw-cli")
        dump = shutil.which("pw-dump")
        record = shutil.which("pw-record")
        if not cli or not dump or not record:
            return False
        self._cleanup_stale_sources(dump)
        try:
            target = None
            if microphone_key is not None:
                result = subprocess.run(
                    [dump],
                    capture_output=True,
                    text=True,
                    timeout=1,
                    check=False,
                )
                if result.returncode:
                    return False
                target = self.resolve_target(microphone_key, json.loads(result.stdout))
                if target is None:
                    return False
            self._target = target
            capture_props = (
                f'capture.props = {{ node.name = "{self._source_name}-capture" '
                "node.dont-fallback = true node.dont-reconnect = true "
                "node.dont-move = true "
                + (f"target.object = {json.dumps(target)} " if target else "")
                + "} "
            )
            process = subprocess.Popen(
                [cli],
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                text=True,
            )
            self._process = process
            self._record = record
            assert process.stdin is not None
            process.stdin.write(
                "load-module libpipewire-module-echo-cancel "
                "{ monitor.mode = true "
                + capture_props
                + f'sink.props = {{ node.name = "{self._source_name}-monitor" }} '
                + f'source.props = {{ node.name = "{self._source_name}" '
                'node.description = "KYRIN echo-cancelled microphone" } }\n'
            )
            process.stdin.flush()
            deadline = time.monotonic() + self._ready_timeout_s
            while time.monotonic() < deadline and process.poll() is None:
                if self._source_exists(dump):
                    return True
                time.sleep(0.05)
        except OSError, ValueError, subprocess.SubprocessError:
            pass
        self.close()
        return False

    @staticmethod
    def resolve_target(key: str, graph: list[dict[str, Any]]) -> str | None:
        """Map only identities with evidence; ambiguous/unknown paths use the guard."""
        try:
            identity = json.loads(key)
        except ValueError, TypeError:
            return None
        if not isinstance(identity, list) or len(identity) != 2:
            return None
        host, name = identity
        if not isinstance(host, str) or not isinstance(name, str):
            return None
        if host == "ALSA" and name in {"pulse", "pipewire"}:
            defaults = [
                prop.get("value")
                for item in graph
                if item.get("type") == "PipeWire:Interface:Metadata"
                for prop in item.get("metadata", [])
                if prop.get("key") == "default.audio.source"
                and prop.get("subject", 0) == 0
            ]
            if len(defaults) != 1:
                return None
            try:
                value = defaults[0]
                if isinstance(value, str):
                    value = json.loads(value)
                if not isinstance(value, dict) or not isinstance(
                    value.get("name"), str
                ):
                    return None
                name = value["name"]
            except ValueError, TypeError:
                return None
            host = "PulseAudio"
        hardware = re.search(r"\(hw:(\d+),(\d+)\)$", name) if host == "ALSA" else None
        matches = []
        for item in graph:
            props = item.get("info", {}).get("props", {})
            if props.get("media.class") != "Audio/Source":
                continue
            node = props.get("node.name")
            if not isinstance(node, str) or node.startswith("kyrin-echo-"):
                continue
            if hardware is not None:
                matched = (
                    str(props.get("api.alsa.pcm.card")) == hardware[1]
                    and str(props.get("api.alsa.pcm.device")) == hardware[2]
                    and not props.get("api.alsa.split.position")
                )
            else:
                matched = host == "PulseAudio" and name in (
                    node,
                    props.get("node.description"),
                )
            if matched:
                matches.append(node)
        return matches[0] if len(matches) == 1 else None

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
        except OSError, ValueError, subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=2)

    def _source_exists(self, executable: str) -> bool:
        result = subprocess.run(
            [executable],
            capture_output=True,
            text=True,
            timeout=1,
            check=False,
        )
        if result.returncode:
            return False
        graph = json.loads(result.stdout)
        nodes = {
            item["id"]: item.get("info", {}).get("props", {})
            for item in graph
            if item.get("type") == "PipeWire:Interface:Node"
        }
        names = {props.get("node.name"): node_id for node_id, props in nodes.items()}
        if self._source_name not in names:
            return False
        capture_id = names.get(f"{self._source_name}-capture")
        monitor_id = names.get(f"{self._source_name}-monitor")
        capture_linked = monitor_linked = False
        for item in graph:
            if item.get("type") != "PipeWire:Interface:Link":
                continue
            info = item.get("info", {})
            if info.get("state") not in {"active", "paused"}:
                continue
            upstream = nodes.get(info.get("output-node-id"), {})
            if info.get("input-node-id") == capture_id and capture_id is not None:
                capture_linked |= upstream.get("media.class") == "Audio/Source" and (
                    self._target is None or upstream.get("node.name") == self._target
                )
            if info.get("input-node-id") == monitor_id and monitor_id is not None:
                monitor_linked |= upstream.get("media.class") == "Audio/Sink"
        return capture_linked and monitor_linked

    @staticmethod
    def _cleanup_stale_sources(executable: str) -> None:
        """Remove only orphaned sources created by older KYRIN processes."""
        try:
            result = subprocess.run(
                [executable],
                capture_output=True,
                text=True,
                timeout=1,
                check=False,
            )
            if result.returncode:
                return
            graph = json.loads(result.stdout)
        except OSError, ValueError, subprocess.TimeoutExpired:
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
            except TypeError, ValueError:
                client_id = 0
            client = clients.get(client_id, {})
            client_props = client.get("info", {}).get("props", {})
            try:
                module_pid = int(client_props.get("pipewire.sec.pid", 0))
            except TypeError, ValueError:
                module_pid = 0
            PipeWireEchoCancellation._terminate_owned_process(module_pid, b"/pw-cli\0")
            for process in Path("/proc").iterdir():
                if not process.name.isdigit():
                    continue
                try:
                    command = (process / "cmdline").read_bytes()
                except OSError:
                    continue
                if (b"/pw-record\0--target\0" + name.encode() + b"\0") in command:
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
        except OSError, ProcessLookupError:
            return
