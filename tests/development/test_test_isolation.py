"""Direct pytest must protect inherited profiles, even outside the full gate."""

import os
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.parametrize("configured_data_home", [False, True])
def test_direct_qt_revocation_preserves_external_profile(
    tmp_path: Path, configured_data_home: bool,
) -> None:
    pytest.importorskip("PySide6")
    root = Path(__file__).resolve().parents[2]
    # This decoy profile is entirely disposable; never inspect real owner tokens.
    home = tmp_path / "outside-profile"
    data = home / ("data" if configured_data_home else ".local/share")
    token = data / "kyrin/permissions/desktop-input.token"
    token.parent.mkdir(parents=True)
    token.write_text("outside-consent-must-survive")
    token.chmod(0o600)
    environment = dict(os.environ)
    environment["HOME"] = str(home)
    environment["PYTHONPATH"] = str(root / "src")
    environment["QT_QPA_PLATFORM"] = "offscreen"
    environment["PYTEST_ADDOPTS"] = ""
    if configured_data_home:
        environment["XDG_DATA_HOME"] = str(data)
    else:
        environment.pop("XDG_DATA_HOME", None)
    for key in ("DBUS_SESSION_BUS_ADDRESS", "DISPLAY", "WAYLAND_DISPLAY"):
        environment.pop(key, None)
    result = subprocess.run(
        [
            sys.executable, "-m", "pytest", "-q",
            "tests/app/test_qt_window.py::"
            "test_window_revocation_stays_inside_test_profile",
            "--basetemp", str(tmp_path / "child-tests"),
        ],
        cwd=root, env=environment, text=True, capture_output=True,
        timeout=60, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "1 passed" in result.stdout
    assert token.read_text() == "outside-consent-must-survive"
