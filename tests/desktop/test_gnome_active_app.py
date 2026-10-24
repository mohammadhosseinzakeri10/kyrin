"""The GNOME adapter never treats an absent or unknown app as verified focus."""

import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from kyrin.desktop.platforms.gnome import (
    ActiveWindowIdentity,
    GnomeShellActiveAppObserver,
)
from kyrin.desktop.platforms.xdg import XdgDesktopAppCatalog
from tests.desktop.test_backend_protocol import bus_reply


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
        side_effect=[
            bus_reply("GetActiveApp"),
            _reply("org.telegram.desktop"),
            bus_reply("GetActiveApp"),
            _reply("unknown.desktop"),
        ],
    ) as run:
        assert observer.observe_active_app() == "telegram"
        assert observer.observe_active_app() is None
    assert run.call_count == 4


def test_catalog_can_reject_a_stale_binding(tmp_path: Path) -> None:
    app_dir = tmp_path / "applications"
    app_dir.mkdir()
    (app_dir / "known.desktop").write_text(
        "[Desktop Entry]\nType=Application\nName=Known\n", encoding="utf-8"
    )
    observer = GnomeShellActiveAppObserver(
        {"known.desktop": "known", "removed.desktop": "removed"},
        catalog=XdgDesktopAppCatalog((tmp_path,)),
    )
    with patch(
        "kyrin.desktop.platforms.gnome.subprocess.run",
        side_effect=[
            bus_reply("GetActiveApp"),
            _reply("known.desktop"),
            bus_reply("GetActiveApp"),
            _reply("removed.desktop"),
        ],
    ):
        assert observer.observe_active_app() == "known"
        assert observer.observe_active_app() is None


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
    with patch(
        "kyrin.desktop.platforms.gnome.subprocess.run",
        side_effect=[bus_reply("GetActiveApp"), reply],
    ):
        assert observer.observe_active_app() is None


def test_bus_timeout_is_unknown() -> None:
    observer = GnomeShellActiveAppObserver({"org.telegram.desktop": "telegram"})
    with patch(
        "kyrin.desktop.platforms.gnome.subprocess.run",
        side_effect=subprocess.TimeoutExpired(cmd="busctl", timeout=1),
    ):
        assert observer.observe_active_app() is None


def test_focused_window_identity_requires_valid_id_and_pid() -> None:
    observer = GnomeShellActiveAppObserver({})
    valid = subprocess.CompletedProcess(
        args=[],
        returncode=0,
        stdout='{"type":"su","data":["telegram.desktop",123]}',
    )
    invalid = subprocess.CompletedProcess(
        args=[],
        returncode=0,
        stdout='{"type":"su","data":["telegram.desktop",0]}',
    )
    with patch(
        "kyrin.desktop.platforms.gnome.subprocess.run",
        side_effect=[
            bus_reply("GetActiveWindow"),
            valid,
            bus_reply("GetActiveWindow"),
            invalid,
        ],
    ):
        assert observer.read_active_window_identity() == ActiveWindowIdentity(
            "telegram.desktop", 123
        )
        assert observer.read_active_window_identity() is None


def test_invalid_configuration_is_rejected() -> None:
    with pytest.raises(ValueError, match="timeout_s"):
        GnomeShellActiveAppObserver({}, timeout_s=0)
    with pytest.raises(ValueError, match="identifiers"):
        GnomeShellActiveAppObserver({"org.telegram.desktop": ""})


def test_optional_active_app_endpoint_is_detected_without_reading_focus() -> None:
    with patch(
        "kyrin.desktop.platforms.gnome.subprocess.run",
        return_value=bus_reply("GetActiveApp"),
    ) as run:
        assert GnomeShellActiveAppObserver.available()
    assert run.call_args.args[0][-3:] == [
        "/org/kyrin/ActiveApp",
        "org.kyrin.ActiveApp",
        "GetCapabilities",
    ]
