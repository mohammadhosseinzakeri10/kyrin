"""GNOME activation accepts only exact registered desktop IDs and parsed replies."""

import subprocess
from unittest.mock import patch

import pytest

from kyrin.desktop.app_activation import ActivationAttempt
from kyrin.desktop.platforms.gnome_activation import GnomeExistingAppActivator
from tests.desktop.test_backend_protocol import bus_reply


def _reply(value: str) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess([], 0, f'{{"type":"s","data":["{value}"]}}')


def test_requests_only_the_bound_desktop_id() -> None:
    activator = GnomeExistingAppActivator({"telegram": "org.telegram.desktop"})
    with patch(
        "kyrin.desktop.platforms.gnome_activation.subprocess.run",
        side_effect=[bus_reply("ActivateExistingApp"), _reply("requested")],
    ) as run:
        assert (
            activator.activate_existing_app("telegram") is ActivationAttempt.REQUESTED
        )
    assert run.call_args.args[0][-3:] == [
        "ActivateExistingApp",
        "s",
        "org.telegram.desktop",
    ]
    assert activator.activate_existing_app("unbound") is ActivationAttempt.UNKNOWN


@pytest.mark.parametrize(
    ("result", "expected"),
    [
        (_reply("no_window"), ActivationAttempt.NO_WINDOW),
        (_reply("multiple_windows"), ActivationAttempt.MULTIPLE_WINDOWS),
        (_reply("surprise"), ActivationAttempt.UNKNOWN),
        (
            subprocess.CompletedProcess([], 0, '{"type":"b","data":[true]}'),
            ActivationAttempt.UNKNOWN,
        ),
        (subprocess.CompletedProcess([], 1, ""), ActivationAttempt.UNKNOWN),
    ],
)
def test_only_explicit_no_window_permits_a_launch(
    result: subprocess.CompletedProcess[str], expected: ActivationAttempt
) -> None:
    activator = GnomeExistingAppActivator({"telegram": "org.telegram.desktop"})
    with patch(
        "kyrin.desktop.platforms.gnome_activation.subprocess.run",
        side_effect=[bus_reply("ActivateExistingApp"), result],
    ):
        assert activator.activate_existing_app("telegram") is expected


def test_timeout_is_uncertain() -> None:
    activator = GnomeExistingAppActivator({"telegram": "org.telegram.desktop"})
    with patch(
        "kyrin.desktop.platforms.gnome_activation.subprocess.run",
        side_effect=subprocess.TimeoutExpired("busctl", 1),
    ):
        assert activator.activate_existing_app("telegram") is ActivationAttempt.UNKNOWN


def test_old_extension_is_not_used_as_an_activator() -> None:
    result = subprocess.CompletedProcess([], 0, "GetActiveApp\nGetActiveWindow\n")
    with patch(
        "kyrin.desktop.platforms.gnome_activation.subprocess.run",
        return_value=result,
    ):
        assert not GnomeExistingAppActivator.available()


def test_invalid_registration_is_rejected() -> None:
    with pytest.raises(ValueError, match="registered"):
        GnomeExistingAppActivator({"telegram": "telegram"})
