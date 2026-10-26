"""Actual Gio/GLib owner and helpers against an isolated synthetic D-Bus portal."""

import json
import os
import subprocess
from pathlib import Path

import pytest


@pytest.mark.parametrize("registry", [False, True])
def test_real_gio_owner_reuses_session_on_private_bus(
    tmp_path: Path, registry: bool
) -> None:
    root = Path(__file__).resolve().parents[2]
    environment = dict(os.environ)
    for key in ("DBUS_SESSION_BUS_ADDRESS", "DISPLAY", "WAYLAND_DISPLAY"):
        environment.pop(key, None)
    for key in ("HOME", "XDG_DATA_HOME", "XDG_CONFIG_HOME", "XDG_RUNTIME_DIR"):
        directory = tmp_path / key.lower()
        directory.mkdir(mode=0o700)
        environment[key] = str(directory)
    if registry:
        environment["KYRIN_TEST_REGISTRY"] = "1"
    else:
        environment.pop("KYRIN_TEST_REGISTRY", None)
    environment["PYTHONPATH"] = str(root / "src")
    result = subprocess.run(
        [
            "dbus-run-session",
            "--",
            "/usr/bin/python3",
            str(Path(__file__).with_name("fixtures") / "input_portal_bus.py"),
        ],
        env=environment,
        capture_output=True,
        text=True,
        timeout=55,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout.strip())
    assert report["counts"]["Start"] == 1
    assert report["one_sender"] and report["one_session"]
