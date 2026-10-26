"""The read-only observer fails closed on missing or changing desktop state."""

import json
import subprocess
from types import SimpleNamespace
from typing import cast
from unittest.mock import patch

from kyrin.desktop.app_catalog import AppCatalog, InstalledApp
from kyrin.desktop.platforms.atspi import UbuntuAtspiScreenObserver
from kyrin.desktop.platforms.gnome import (
    ActiveWindowIdentity,
    GnomeShellActiveAppObserver,
)


class FakeCatalog:
    def find_app(self, platform_id: str) -> InstalledApp | None:
        if platform_id == "telegram.desktop":
            return InstalledApp(platform_id, "Telegram")
        return None


class FakeActiveApp:
    def __init__(self, *identities: ActiveWindowIdentity | None) -> None:
        self._identities = iter(identities)

    def read_active_window_identity(self) -> ActiveWindowIdentity | None:
        return next(self._identities)


def identity(app_id: str = "telegram.desktop", pid: int = 123) -> ActiveWindowIdentity:
    return ActiveWindowIdentity(app_id, pid)


def make_observer(
    *identities: ActiveWindowIdentity | None,
) -> UbuntuAtspiScreenObserver:
    return UbuntuAtspiScreenObserver(
        cast(AppCatalog, FakeCatalog()),
        cast(GnomeShellActiveAppObserver, FakeActiveApp(*identities)),
    )


def result(payload: object, returncode: int = 0) -> SimpleNamespace:
    return SimpleNamespace(stdout=json.dumps(payload), returncode=returncode)


def test_observes_bounded_labels_without_executing_actions() -> None:
    payload = {
        "status": "ok",
        "app_name": "Telegram",
        "elements": [{"role": "push button", "name": "Search"}],
        "truncated": False,
    }
    with patch(
        "kyrin.desktop.platforms.atspi.subprocess.run", return_value=result(payload)
    ):
        observation = make_observer(identity(), identity()).observe()
    assert observation is not None
    assert observation.platform_app_id == "telegram.desktop"
    assert [(item.role, item.name) for item in observation.elements] == [
        ("push button", "Search")
    ]


def test_rejects_focus_change_during_observation() -> None:
    payload = {
        "status": "ok",
        "app_name": "Telegram",
        "elements": [],
        "truncated": False,
    }
    with patch(
        "kyrin.desktop.platforms.atspi.subprocess.run", return_value=result(payload)
    ):
        assert make_observer(identity(), identity("browser.desktop")).observe() is None


def test_rejects_unregistered_app_before_starting_probe() -> None:
    with patch("kyrin.desktop.platforms.atspi.subprocess.run") as run:
        assert make_observer(identity("unknown.desktop")).observe() is None
    run.assert_not_called()


def test_rejects_ambiguous_or_malformed_probe_output() -> None:
    with patch(
        "kyrin.desktop.platforms.atspi.subprocess.run",
        return_value=result({"status": "unavailable"}),
    ):
        assert make_observer(identity()).observe() is None
    with patch(
        "kyrin.desktop.platforms.atspi.subprocess.run",
        return_value=result(
            {"status": "ok", "app_name": "", "elements": [], "truncated": False}
        ),
    ):
        assert make_observer(identity()).observe() is None


def test_probe_timeout_is_unknown() -> None:
    with patch(
        "kyrin.desktop.platforms.atspi.subprocess.run",
        side_effect=subprocess.TimeoutExpired("python", 8),
    ):
        assert make_observer(identity()).observe() is None
