"""The GNOME adapter never treats an absent or unknown app as verified focus."""

import subprocess
from unittest.mock import patch

import pytest

from kyrin.desktop.platforms.gnome import GnomeShellActiveAppObserver


def _reply(app_id: str) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(
        args=[], returncode=0, stdout=f'{{"type":"s","data":["{app_id}"]}}'
    )


def test_each_observation_reads_fresh_focus_and_maps_only_known_apps() -> None:
    observer = GnomeShellActiveAppObserver(
        {"org.telegram.desktop": "telegram", "google-chrome.desktop": "browser"}
    )
    with patch(
        "kyrin.desktop.platforms.gnome.subprocess.run",
        side_effect=[_reply("org.telegram.desktop"), _reply("unknown.desktop")],
    ) as run:
        assert observer.observe_active_app() == "telegram"
        assert observer.observe_active_app() is None
    assert run.call_count == 2


@pytest.mark.parametrize(
    "reply",
    [
        subprocess.CompletedProcess(args=[], returncode=1, stdout=""),
        subprocess.CompletedProcess(args=[], returncode=0, stdout="not-json"),
        subprocess.CompletedProcess(
            args=[], returncode=0, stdout='{"type":"s","data":[""]}'
        ),
        subprocess.CompletedProcess(
            args=[], returncode=0, stdout='{"type":"u","data":[1]}'
        ),
    ],
)
def test_missing_or_invalid_focus_is_unknown(
    reply: subprocess.CompletedProcess[str],
) -> None:
    observer = GnomeShellActiveAppObserver({"org.telegram.desktop": "telegram"})
    with patch("kyrin.desktop.platforms.gnome.subprocess.run", return_value=reply):
        assert observer.observe_active_app() is None


def test_bus_timeout_is_unknown() -> None:
    observer = GnomeShellActiveAppObserver({"org.telegram.desktop": "telegram"})
    with patch(
        "kyrin.desktop.platforms.gnome.subprocess.run",
        side_effect=subprocess.TimeoutExpired(cmd="busctl", timeout=1),
    ):
        assert observer.observe_active_app() is None


def test_invalid_configuration_is_rejected() -> None:
    with pytest.raises(ValueError, match="timeout_s"):
        GnomeShellActiveAppObserver({}, timeout_s=0)
    with pytest.raises(ValueError, match="identifiers"):
        GnomeShellActiveAppObserver({"org.telegram.desktop": ""})
