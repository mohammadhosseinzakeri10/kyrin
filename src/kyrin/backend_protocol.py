"""Versioned, input-free negotiation shared by Shell and system-Python helpers.

Build IDs describe the responding code, never extension metadata on disk.
No successful result is cached across operations or a Shell reload.
"""

from __future__ import annotations

import json
import subprocess
from collections.abc import Callable, Set
from dataclasses import dataclass
from time import sleep
from typing import Any

PROTOCOL_VERSION = 1


@dataclass(frozen=True)
class BackendStatus:
    ready: bool
    reason: str
    protocol_version: int | None = None
    build_id: str | None = None
    capabilities: frozenset[str] = frozenset()


class BackendUnavailable(OSError):
    def __init__(self, status: BackendStatus) -> None:
        self.status = status
        super().__init__(status.reason)


def assess(payload: str, required: Set[str]) -> BackendStatus:
    try:
        value = json.loads(payload)
    except ValueError, TypeError:
        return BackendStatus(False, "malformed_handshake")
    if not isinstance(value, dict):
        return BackendStatus(False, "malformed_handshake")
    version = value.get("protocol_version")
    build = value.get("build_id")
    caps = value.get("capabilities")
    if (
        type(version) is not int
        or not isinstance(build, str)
        or not build.strip()
        or not isinstance(caps, list)
        or any(not isinstance(cap, str) or not cap for cap in caps)
    ):
        return BackendStatus(False, "malformed_handshake")
    capabilities = frozenset(caps)
    reason = "ready"
    if version != PROTOCOL_VERSION:
        reason = "protocol_mismatch"
    elif missing := required - capabilities:
        reason = "missing_capabilities:" + ",".join(sorted(missing))
    return BackendStatus(reason == "ready", reason, version, build, capabilities)


def bus_status(arguments: object, required: Set[str]) -> BackendStatus:
    if (
        not isinstance(arguments, list)
        or len(arguments) != 1
        or not isinstance(arguments[0], str)
    ):
        return BackendStatus(False, "malformed_handshake")
    return assess(arguments[0], required)


def transport_status(error: str) -> BackendStatus:
    if "UnknownMethod" in error or "No such method" in error:
        return BackendStatus(False, "handshake_missing")
    if "AccessDenied" in error or "AuthFailed" in error or "Access denied" in error:
        return BackendStatus(False, "access_denied")
    if "NoReply" in error or "Timeout" in error or "timed out" in error:
        return BackendStatus(False, "service_timeout")
    return BackendStatus(False, "service_unavailable")


def probe_gnome(
    endpoint: str,
    required: Set[str],
    *,
    run: Callable[..., subprocess.CompletedProcess[Any]],
    attempts: int = 3,
    retry_delay_s: float = 0.05,
) -> BackendStatus:
    """Retry only missing/timed-out services; never retry an input operation."""
    if attempts < 1 or retry_delay_s < 0:
        raise ValueError("invalid probe retries")
    status = BackendStatus(False, "service_unavailable")
    for attempt in range(attempts):
        if attempt:
            sleep(retry_delay_s)
        try:
            result = run(
                [
                    "busctl",
                    "--user",
                    "--json=short",
                    "call",
                    "org.gnome.Shell",
                    "/org/kyrin/" + endpoint,
                    "org.kyrin." + endpoint,
                    "GetCapabilities",
                ],
                capture_output=True,
                text=True,
                check=False,
                timeout=0.5,
            )
        except subprocess.TimeoutExpired:
            status = BackendStatus(False, "service_timeout")
            continue
        except FileNotFoundError:
            return BackendStatus(False, "transport_missing")
        except PermissionError:
            return BackendStatus(False, "access_denied")
        except OSError:
            return BackendStatus(False, "transport_unavailable")
        if result.returncode:
            status = transport_status(result.stderr or "")
            if status.reason in {"service_unavailable", "service_timeout"}:
                continue
            return status
        try:
            reply = json.loads(result.stdout)
        except ValueError, TypeError:
            return BackendStatus(False, "malformed_handshake")
        if not isinstance(reply, dict) or reply.get("type") != "s":
            return BackendStatus(False, "malformed_handshake")
        return bus_status(reply.get("data", []), required)
    return status


def helper_manifest(capability: str) -> str:
    return json.dumps(
        {
            "protocol_version": PROTOCOL_VERSION,
            "build_id": capability + "-2026-10-24-f20",
            "capabilities": [capability],
        }
    )


def backend_error(backend: object) -> str | None:
    """Optional diagnostics leave platform-neutral result contracts intact."""
    status = getattr(backend, "backend_status", None)
    if (
        isinstance(status, BackendStatus)
        and not status.ready
        and status.reason != "not_probed"
    ):
        return "backend:" + status.reason
    return None
