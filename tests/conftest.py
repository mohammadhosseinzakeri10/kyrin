"""Keep direct test runs outside the developer's real application profile."""

from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def isolated_profile(
    tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch,
) -> Path:
    """Apply the full gate's profile boundary even for a single pytest node."""
    profile = tmp_path_factory.mktemp("profile")
    for variable, name in (
        ("HOME", "home"),
        ("XDG_CONFIG_HOME", "config"),
        ("XDG_DATA_HOME", "data"),
        ("XDG_CACHE_HOME", "cache"),
        ("XDG_STATE_HOME", "state"),
        ("XDG_RUNTIME_DIR", "runtime"),
    ):
        directory = profile / name
        directory.mkdir(parents=True, mode=0o700)
        monkeypatch.setenv(variable, str(directory))
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("HF_HUB_OFFLINE", "1")
    monkeypatch.setenv("TRANSFORMERS_OFFLINE", "1")
    monkeypatch.setenv("HF_HOME", str(profile / "cache/huggingface"))
    for variable in ("DBUS_SESSION_BUS_ADDRESS", "DISPLAY", "WAYLAND_DISPLAY"):
        monkeypatch.delenv(variable, raising=False)
    return profile
