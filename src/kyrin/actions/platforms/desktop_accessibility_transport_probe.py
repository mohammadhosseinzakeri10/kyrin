"""Opt-in, read-only wire comparison for a missing accessibility child.

Only fixed count/child methods are called. References and errors stay private;
the returned counters cannot authorize an action or repair a partial snapshot.
"""

import json
import subprocess
from typing import Any

from kyrin.actions.platforms.desktop_accessibility import _remote_reference

ACCESSIBLE = "org.a11y.atspi.Accessible"
NULL_PATH = "/org/a11y/atspi/null"


def _read_json(arguments: list[str]) -> dict[str, Any] | None:
    try:
        result = subprocess.run(
            ["busctl", *arguments],
            capture_output=True,
            text=True,
            stdin=subprocess.DEVNULL,
            timeout=1,
            check=False,
        )
        if result.returncode or len(result.stdout) > 512_000:
            return None
        payload = json.loads(result.stdout)
    except OSError, subprocess.TimeoutExpired, ValueError:
        return None
    return payload if isinstance(payload, dict) else None


def _value(reply: dict[str, Any] | None, signature: str) -> Any:
    if (
        reply is not None
        and reply.get("type") == signature
        and isinstance(reply.get("data"), list)
        and len(reply["data"]) == 1
    ):
        return reply["data"][0]
    return None


def _is_reference(value: object) -> bool:
    return (
        isinstance(value, list)
        and len(value) == 2
        and isinstance(value[0], str)
        and isinstance(value[1], str)
        and value[1].startswith("/")
    )


def probe_missing_child(node: Any, index: int) -> dict[str, int]:
    reference = _remote_reference(node)
    if reference is None:
        return {"wire_reference_unavailable": 1}
    bus_name, path = reference
    address = _value(
        _read_json(
            [
                "--user",
                "--json=short",
                "call",
                "org.a11y.Bus",
                "/org/a11y/bus",
                "org.a11y.Bus",
                "GetAddress",
            ]
        ),
        "s",
    )
    if not isinstance(address, str) or not address.startswith("unix:"):
        return {"wire_address_unavailable": 1}
    prefix = ["--address=" + address, "--json=short"]
    owner = _value(
        _read_json(
            [
                *prefix,
                "call",
                "org.freedesktop.DBus",
                "/org/freedesktop/DBus",
                "org.freedesktop.DBus",
                "GetConnectionUnixProcessID",
                "s",
                bus_name,
            ]
        ),
        "u",
    )
    if type(owner) is not int or owner <= 0 or owner != node.get_process_id():
        return {"wire_owner_matches": 0}
    metrics = {"wire_owner_matches": 1}
    count_reply = _read_json(
        [*prefix, "get-property", bus_name, path, ACCESSIBLE, "ChildCount"]
    )
    # busctl get-property encodes a scalar directly; call wraps output arguments.
    count = (
        count_reply.get("data")
        if count_reply is not None and count_reply.get("type") == "i"
        else None
    )
    if type(count) is int and 0 <= count <= 3000:
        metrics["wire_child_count"] = count
    else:
        metrics["wire_child_count_unavailable"] = 1
    child = _value(
        _read_json(
            [
                *prefix,
                "call",
                bus_name,
                path,
                ACCESSIBLE,
                "GetChildAtIndex",
                "i",
                str(index),
            ]
        ),
        "(so)",
    )
    if _is_reference(child):
        metrics["wire_child_is_null"] = int(child[1] == NULL_PATH)
    else:
        metrics["wire_child_unavailable"] = 1
    children = _value(
        _read_json([*prefix, "call", bus_name, path, ACCESSIBLE, "GetChildren"]),
        "a(so)",
    )
    if (
        isinstance(children, list)
        and len(children) <= 3000
        and all(_is_reference(item) for item in children)
    ):
        metrics["wire_children_count"] = len(children)
        metrics["wire_children_nulls"] = sum(item[1] == NULL_PATH for item in children)
        if _is_reference(child) and 0 <= index < len(children):
            metrics["wire_index_agrees_with_children"] = int(child == children[index])
    else:
        metrics["wire_children_unavailable"] = 1
    return metrics
