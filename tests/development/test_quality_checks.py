"""Quality checks must report failures without skipping subsequent checks."""

import json
import os
import subprocess
from pathlib import Path
from typing import TextIO

import pytest

from scripts.development.check import run_checks


@pytest.mark.parametrize("failed", [None, "syntax", "lint", "type", "tests"])
def test_checks_preserve_failures_and_run_every_stage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failed: str | None
) -> None:
    commands: list[list[str]] = []
    environments: list[dict[str, str]] = []

    def run(
        command: list[str], *, cwd: Path, env: dict[str, str],
        stdout: TextIO, stderr: int, check: bool,
    ) -> subprocess.CompletedProcess[str]:
        stage = ["syntax", "lint", "type", "tests"][len(commands)]
        commands.append(command)
        environments.append(env)
        stdout.write(f"{stage} output\n")
        assert cwd == Path(__file__).resolve().parents[2]
        assert stderr == subprocess.STDOUT and not check
        if stage == "tests":
            assert Path(env["HOME"]).is_dir()
            assert env["QT_QPA_PLATFORM"] == "offscreen"
            assert "DBUS_SESSION_BUS_ADDRESS" not in env
            assert "WAYLAND_DISPLAY" not in env
        return subprocess.CompletedProcess(command, 1 if stage == failed else 0)

    monkeypatch.setenv("DBUS_SESSION_BUS_ADDRESS", "private-owner-bus")
    monkeypatch.setenv("WAYLAND_DISPLAY", "private-owner-display")
    original = dict(os.environ)
    monkeypatch.setattr(subprocess, "run", run)
    assert run_checks(tmp_path) == (1 if failed else 0)
    assert len(commands) == 4
    assert commands[0][-3:] == ["src", "tests", "scripts"]
    assert commands[1][-3:] == ["src", "tests", "scripts"]
    assert commands[2][-3:] == ["src", "tests", "scripts"]
    assert commands[3][-3:] == ["pytest", "-q", "tests"]
    summary = json.loads((tmp_path / "summary.json").read_text())
    assert summary == {
        stage: (1 if stage == failed else 0)
        for stage in ["syntax", "lint", "type", "tests"]
    }
    assert (tmp_path / "type.log").read_text() == "type output\n"
    assert dict(os.environ) == original
    assert not Path(environments[-1]["HOME"]).exists()
