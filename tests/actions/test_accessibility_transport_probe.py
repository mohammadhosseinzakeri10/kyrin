"""A missing-child wire probe discloses counters and never sends input."""

import json
import subprocess
from types import SimpleNamespace

import pytest

from kyrin.actions.platforms.desktop_accessibility_transport_probe import (
    NULL_PATH,
    probe_missing_child,
)


@pytest.mark.parametrize(
    "child,children,is_null,agrees",
    [
        (["", NULL_PATH], [[":private", "/private/child"]], 1, 0),
        ([":private", "/private/child"], [[":private", "/private/child"]], 0, 1),
        (["", NULL_PATH], [["", NULL_PATH]], 1, 1),
    ],
)
def test_wire_probe_compares_indexed_and_bulk_reads_without_exporting_references(
    monkeypatch: pytest.MonkeyPatch,
    child: list[str],
    children: list[list[str]],
    is_null: int,
    agrees: int,
) -> None:
    calls: list[list[str]] = []

    def run(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(args)
        assert kwargs["timeout"] == 1
        assert kwargs["stdin"] == subprocess.DEVNULL
        data: object
        if args[-1] == "GetAddress":
            signature, data = "s", ["unix:path=/private/bus"]
        elif "GetConnectionUnixProcessID" in args:
            signature, data = "u", [42]
        elif "get-property" in args:
            assert args[-1] == "ChildCount"
            signature, data = "i", len(children)
        elif "GetChildAtIndex" in args:
            assert args[-2:] == ["i", "0"]
            signature, data = "(so)", [child]
        else:
            assert args[-1] == "GetChildren", "unexpected mutation or call"
            signature, data = "a(so)", [children]
        return subprocess.CompletedProcess(
            args, 0, json.dumps({"type": signature, "data": data}), "private stderr"
        )

    monkeypatch.setattr(subprocess, "run", run)
    node = SimpleNamespace(
        path="/private/root",
        app=SimpleNamespace(bus_name=":private"),
        get_process_id=lambda: 42,
    )
    metrics = probe_missing_child(node, 0)
    assert len(calls) == 5
    assert metrics["wire_owner_matches"] == 1
    assert metrics["wire_child_count"] == len(children)
    assert metrics["wire_child_is_null"] == is_null
    assert metrics["wire_children_count"] == len(children)
    assert metrics["wire_index_agrees_with_children"] == agrees
    assert "private" not in str(metrics)


@pytest.mark.parametrize(
    "failure",
    [
        "timeout",
        "unavailable",
        "stderr",
        "invalid_json",
        "remote_address",
        "wrong_owner",
    ],
)
def test_wire_probe_failures_are_bounded_and_sanitized(
    monkeypatch: pytest.MonkeyPatch,
    failure: str,
) -> None:
    calls: list[list[str]] = []

    def run(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(args)
        if failure == "timeout":
            raise subprocess.TimeoutExpired(args, 1)
        if failure == "unavailable":
            raise FileNotFoundError("private path")
        if failure == "stderr":
            return subprocess.CompletedProcess(args, 1, "", "private failure")
        if failure == "invalid_json":
            return subprocess.CompletedProcess(args, 0, "private invalid json", "")
        reply: dict[str, object]
        if args[-1] == "GetAddress":
            reply = {
                "type": "s",
                "data": [
                    "tcp:private"
                    if failure == "remote_address"
                    else "unix:path=/private/bus"
                ],
            }
        else:
            assert "GetConnectionUnixProcessID" in args
            reply = {"type": "u", "data": [99]}
        return subprocess.CompletedProcess(args, 0, json.dumps(reply), "")

    monkeypatch.setattr(subprocess, "run", run)
    node = SimpleNamespace(
        path="/private/root",
        app=SimpleNamespace(bus_name=":private"),
        get_process_id=lambda: 42,
    )
    metrics = probe_missing_child(node, 0)
    assert metrics == (
        {"wire_owner_matches": 0}
        if failure == "wrong_owner"
        else {"wire_address_unavailable": 1}
    )
    assert len(calls) == (2 if failure == "wrong_owner" else 1)
    assert "private" not in str(metrics)


def test_wire_probe_does_not_guess_unavailable_endpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        subprocess, "run", lambda *_a, **_kw: pytest.fail("no endpoint")
    )
    assert probe_missing_child(SimpleNamespace(), 0) == {
        "wire_reference_unavailable": 1
    }
