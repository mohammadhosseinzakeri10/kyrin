"""Optional AEC fails closed when PipeWire tools are absent."""

import json
import subprocess

import pytest

from kyrin.app.platforms.pipewire_aec import PipeWireEchoCancellation


def test_missing_pipewire_tools_leave_echo_cancellation_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import shutil

    monkeypatch.setattr(shutil, "which", lambda name: None)
    session = PipeWireEchoCancellation()
    assert not session.start()
    session.close()


def test_stale_cleanup_preserves_sources_owned_by_a_running_kyrin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    graph = [
        {"id": 1, "info": {"props": {
            "node.name": "kyrin-echo-1001-abcdef12", "client.id": 3,
        }}},
        {"id": 2, "info": {"props": {
            "node.name": "kyrin-echo-1002-abcdef12", "client.id": 4,
        }}},
        {"id": 3, "info": {"props": {"pipewire.sec.pid": 2001}}},
        {"id": 4, "info": {"props": {"pipewire.sec.pid": 2002}}},
    ]
    monkeypatch.setattr(
        subprocess, "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args[0], 0, json.dumps(graph), ""
        ),
    )
    monkeypatch.setattr(
        PipeWireEchoCancellation,
        "_is_live_kyrin",
        lambda pid: pid == 1001,
    )
    terminated: list[int] = []
    monkeypatch.setattr(
        PipeWireEchoCancellation,
        "_terminate_owned_process",
        lambda pid, executable: terminated.append(pid),
    )
    PipeWireEchoCancellation._cleanup_stale_sources("pw-dump")
    assert terminated == [2002]
