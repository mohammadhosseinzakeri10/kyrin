"""Ollama memory-placement evidence, never processor-utilization telemetry."""

import errno
import io
import json
import select
import socket
from dataclasses import dataclass
from enum import StrEnum
from http.client import HTTPResponse
from time import monotonic
from typing import cast
from urllib.parse import urlsplit

from kyrin.operations import remaining
from kyrin.stt.device import DevicePreference


class ModelPlacement(StrEnum):
    CPU = "cpu"
    GPU = "gpu"
    MIXED = "mixed"
    GPU_PARTICIPATION = "gpu_participation"
    UNKNOWN = "unknown"


class ModelPresence(StrEnum):
    LOADED = "loaded"
    NOT_LOADED = "not_loaded"
    UNKNOWN = "unknown"


class CleanupState(StrEnum):
    NOT_REQUESTED = "not_requested"
    ACKNOWLEDGED = "acknowledged"
    UNCONFIRMED = "unconfirmed"


class InferenceState(StrEnum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class DeviceObservation:
    placement: ModelPlacement = ModelPlacement.UNKNOWN
    presence: ModelPresence = ModelPresence.UNKNOWN
    reason: str = "unavailable"


@dataclass(frozen=True, slots=True)
class CommandDeviceReport:
    model: str
    requested: DevicePreference
    state: InferenceState
    observation: DeviceObservation = DeviceObservation()
    # Observation precedes cleanup. An unload acknowledgement does not prove
    # memory release: Ollama expires the runner asynchronously.
    residency: ModelPresence = ModelPresence.UNKNOWN
    reason: str = ""
    cleanup: CleanupState = CleanupState.NOT_REQUESTED


def parse_running_device(document: object, model: str) -> DeviceObservation:
    """Use exact selected tags, and Ollama ps's runtime-memory classification.

    size is runtime memory from /api/ps, NOT the /api/tags weight-file size.
    See Ollama v0.31.1 cmd.ListRunningHandler and server.PsHandler.
    """
    if not isinstance(document, dict) or not isinstance(document.get("models"), list):
        return DeviceObservation(reason="invalid_document")
    rows = document["models"]
    if any(
        not isinstance(row, dict)
        or not isinstance(row.get("name"), str)
        or not row["name"]
        for row in rows
    ):
        return DeviceObservation(reason="invalid_document")
    matches = [row for row in rows if row.get("name") == model]
    if not matches:
        return DeviceObservation(presence=ModelPresence.NOT_LOADED, reason="not_loaded")
    if len(matches) != 1:
        return DeviceObservation(reason="ambiguous_identity")
    row = matches[0]
    if row.get("model", model) != model:
        return DeviceObservation(reason="identity_mismatch")
    vram, total = row.get("size_vram"), row.get("size")
    if type(vram) is not int or vram < 0:
        return DeviceObservation(presence=ModelPresence.LOADED, reason="invalid_vram")
    if "size" not in row:
        # Partial evidence proves GPU participation only, never pure CPU/GPU.
        return DeviceObservation(
            ModelPlacement.GPU_PARTICIPATION if vram > 0 else ModelPlacement.UNKNOWN,
            ModelPresence.LOADED,
            "partial_memory",
        )
    if type(total) is not int or total <= 0 or vram > total:
        return DeviceObservation(presence=ModelPresence.LOADED, reason="invalid_memory")
    placement = (
        ModelPlacement.CPU
        if vram == 0
        else ModelPlacement.GPU
        if vram == total
        else ModelPlacement.MIXED
    )
    return DeviceObservation(placement, ModelPresence.LOADED, "ollama_ps_memory")


class _BufferedSocket:
    def __init__(self, data: bytes) -> None:
        self.data = data

    def makefile(self, mode: str) -> io.BytesIO:
        return io.BytesIO(self.data)


def _get_running_models(url: str, timeout: float) -> object:
    """One bounded GET, with cancellation checks even while a peer is silent.

    The owned endpoint is numeric loopback: no DNS, proxies, redirects, retries,
    runner loads, or detached worker threads. A slow trickle cannot renew time.
    """
    endpoint = urlsplit(url)
    if endpoint.scheme != "http" or endpoint.hostname != "127.0.0.1":
        raise ValueError("device observation requires the owned loopback server")
    remaining(timeout)
    deadline = monotonic() + timeout

    def wait(sock: socket.socket, *, writing: bool = False) -> None:
        while True:
            available = min(deadline - monotonic(), remaining(timeout))
            if available <= 0:
                raise TimeoutError("device observation timed out")
            readable, writable, _ = select.select(
                [] if writing else [sock],
                [sock] if writing else [],
                [],
                min(available, 0.05),
            )
            # Scheduling can resume after the deadline even when select says
            # EOF/data is ready. Do not accept a late completion as evidence.
            remaining(timeout)
            if monotonic() >= deadline:
                raise TimeoutError("device observation timed out")
            if readable or writable:
                return

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setblocking(False)
        code = sock.connect_ex(("127.0.0.1", endpoint.port or 80))
        if code not in (0, errno.EINPROGRESS, errno.EWOULDBLOCK):
            raise OSError(code, "device observation connection failed")
        wait(sock, writing=True)
        if sock.getsockopt(socket.SOL_SOCKET, socket.SO_ERROR):
            raise OSError("device observation connection failed")
        request = memoryview(
            f"GET /api/ps HTTP/1.1\r\nHost: {endpoint.netloc}\r\n"
            "Connection: close\r\n\r\n".encode("ascii")
        )
        while request:
            wait(sock, writing=True)
            request = request[sock.send(request) :]
        data = bytearray()
        while True:
            wait(sock)
            chunk = sock.recv(65536)
            if not chunk:
                break
            data.extend(chunk)
            if len(data) > 1024 * 1024:
                raise ValueError("device observation response too large")
        remaining(timeout)
    # HTTPResponse's nominal socket annotation is narrower than the makefile
    # interface it uses. Parse buffered bytes only; no second socket/network read.
    with HTTPResponse(cast(socket.socket, _BufferedSocket(bytes(data)))) as response:
        response.begin()
        if response.status != 200:
            raise ValueError("device observation HTTP failure")
        return json.loads(response.read())


def running_device(url: str, model: str, timeout: float) -> DeviceObservation:
    return parse_running_device(_get_running_models(url, timeout), model)
