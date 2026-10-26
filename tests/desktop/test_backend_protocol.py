"""Negotiate loaded code, never disk metadata or a speculative input call."""

import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest


def manifest(*capabilities: str, version: int = 1) -> str:
    return json.dumps(
        {
            "protocol_version": version,
            "build_id": "loaded-test-build",
            "capabilities": list(capabilities),
        }
    )


def bus_reply(*caps: str, version: int = 1) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(
        [],
        0,
        json.dumps(
            {
                "type": "s",
                "data": [manifest(*caps, version=version)],
            }
        ),
    )


@pytest.mark.parametrize(
    ("payload", "reason"),
    [
        (manifest("GetActiveApp", version=0), "protocol_mismatch"),
        (manifest("OtherMethod"), "missing_capabilities:GetActiveApp"),
        ("{}", "malformed_handshake"),
        (
            manifest("GetActiveApp").replace('"build_id"', '"installed_version"'),
            "malformed_handshake",
        ),
    ],
)
def test_handshake_rejects_old_incomplete_or_disk_only_metadata(
    payload: str, reason: str
) -> None:
    from kyrin.backend_protocol import assess

    status = assess(payload, {"GetActiveApp"})
    assert not status.ready
    assert status.reason == reason


def test_probe_retries_only_read_only_handshake_and_recovers() -> None:
    from kyrin.backend_protocol import probe_gnome

    calls = []
    replies = iter(
        [
            subprocess.CompletedProcess([], 1, "", "UnknownObject"),
            bus_reply("GetActiveApp"),
        ]
    )

    def run(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(args)
        return next(replies)

    status = probe_gnome("ActiveApp", {"GetActiveApp"}, run=run, retry_delay_s=0)
    assert status.ready and status.build_id == "loaded-test-build"
    assert len(calls) == 2
    assert all(call[-1] == "GetCapabilities" for call in calls)


def test_unavailable_is_bounded_and_next_probe_can_recover() -> None:
    from kyrin.backend_protocol import probe_gnome

    with patch(
        "subprocess.run",
        return_value=subprocess.CompletedProcess(
            [], 1, "", "org.freedesktop.DBus.Error.UnknownMethod"
        ),
    ) as run:
        status = probe_gnome("ActiveApp", {"GetActiveApp"}, run=run, retry_delay_s=0)
        assert status.reason == "handshake_missing"
        assert run.call_count == 1
    with patch(
        "subprocess.run",
        return_value=subprocess.CompletedProcess(
            [], 1, "", "org.freedesktop.DBus.Error.UnknownObject"
        ),
    ) as run:
        status = probe_gnome("ActiveApp", {"GetActiveApp"}, run=run, retry_delay_s=0)
        assert status.reason == "service_unavailable"
        assert run.call_count == 3
    with patch("subprocess.run", return_value=bus_reply("GetActiveApp")) as run:
        assert probe_gnome("ActiveApp", {"GetActiveApp"}, run=run).ready


def test_incompatible_activator_never_dispatches_and_recovers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from kyrin.desktop.app_activation import ActivationAttempt
    from kyrin.desktop.platforms.gnome_activation import GnomeExistingAppActivator

    activator = GnomeExistingAppActivator({"test": "test.desktop"})
    calls = []
    ready = False

    def run(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(args[-1])
        if args[-1] == "GetCapabilities":
            return bus_reply("ActivateExistingApp" if ready else "GetActiveApp")
        return subprocess.CompletedProcess([], 0, '{"type":"s","data":["requested"]}')

    monkeypatch.setattr(subprocess, "run", run)
    assert activator.activate_existing_app("test") is ActivationAttempt.UNKNOWN
    assert calls == ["GetCapabilities"]
    assert activator.backend_status.reason == "missing_capabilities:ActivateExistingApp"
    ready = True
    assert activator.activate_existing_app("test") is ActivationAttempt.REQUESTED
    assert calls[-2:] == ["GetCapabilities", "test.desktop"]


@pytest.mark.parametrize(
    "name", ["desktop_control", "desktop_scroll", "telegram_portal"]
)
def test_helper_advertises_version_without_gnome_or_input(name: str) -> None:
    from kyrin.backend_protocol import assess

    helper = Path(__file__).resolve().parents[2] / (
        f"src/kyrin/actions/platforms/{name}_helper.py"
    )
    result = subprocess.run(
        [sys.executable, str(helper), "--capabilities"],
        capture_output=True,
        text=True,
        timeout=5,
    )
    assert result.returncode == 0, result.stderr
    assert assess(result.stdout, {name + "-v1"}).ready


def test_old_helper_cannot_execute_input_and_new_helper_recovers(
    tmp_path: Path,
) -> None:
    from kyrin.backend_protocol import BackendUnavailable
    from kyrin.operations import run_process

    script = tmp_path / "helper.py"
    marker = tmp_path / "input"
    # Old executable exits without a handshake. Input mode must never run.
    script.write_text(
        "import sys\nfrom pathlib import Path\n"
        f"if '--capabilities' not in sys.argv: Path({str(marker)!r}).touch()\n"
    )
    args = [sys.executable, str(script), "input"]
    with pytest.raises(BackendUnavailable, match="malformed_handshake"):
        run_process(args, timeout=2, helper=True, helper_capabilities={"test-v1"})
    assert not marker.exists()
    script.write_text(
        "import sys\nfrom pathlib import Path\n"
        f"if '--capabilities' in sys.argv: print({manifest('test-v1')!r})\n"
        f"else: Path({str(marker)!r}).touch()\n"
    )
    assert (
        run_process(
            args, timeout=2, helper=True, helper_capabilities={"test-v1"}
        ).returncode
        == 0
    )
    assert marker.exists()


@pytest.mark.parametrize(
    "extension_name",
    [
        "active-app",
        "window-capture-prototype",
        "visual-status",
    ],
)
def test_loaded_extension_reports_its_own_complete_contract_without_enable(
    extension_name: str,
) -> None:
    import re
    import shutil

    gjs = shutil.which("gjs")
    if gjs is None:
        pytest.skip("GJS is not installed")
    path = Path(__file__).resolve().parents[2] / (
        f"integrations/gnome-shell/{extension_name}@kyrin.local/extension.js"
    )
    source = path.read_text()
    methods = set(re.findall(r'<method name="([^"]+)"', source)) - {"GetCapabilities"}
    stripped = "\n".join(
        line for line in source.splitlines() if not line.startswith("import ")
    ).replace("export default class", "class")
    match = re.search(r"export default class (\w+)", source)
    assert match is not None
    class_name = match.group(1)
    # Neither enable nor any Shell/portal/permission operation is available.
    result = subprocess.run(
        [
            gjs,
            "-c",
            "class Extension {}\nconst GLib = {"
            "get_user_data_dir: () => '/unopened', "
            "build_filenamev: p => p.join('/')};\n"
            + stripped
            + f"\nprint(new {class_name}().GetCapabilities());",
        ],
        capture_output=True,
        text=True,
        timeout=5,
    )
    assert result.returncode == 0, result.stderr
    from kyrin.backend_protocol import assess

    status = assess(result.stdout, methods)
    assert status.ready
    assert status.build_id is not None
    assert status.build_id.startswith(extension_name + "@kyrin.local-")
    if extension_name == "window-capture-prototype":
        assert "capture-geometry-v1" in status.capabilities


@pytest.mark.parametrize("required", [{"desktop_scroll-v1"}, {"missing-v2"}])
def test_helper_incomplete_capability_is_rejected_before_input(
    tmp_path: Path, required: set[str]
) -> None:
    from kyrin.backend_protocol import BackendUnavailable
    from kyrin.operations import run_process

    marker = tmp_path / "input"
    script = tmp_path / "helper.py"
    script.write_text(
        "import sys\nfrom pathlib import Path\n"
        f"if '--capabilities' in sys.argv: print({manifest('other-v1')!r})\n"
        f"else: Path({str(marker)!r}).touch()\n"
    )
    with pytest.raises(BackendUnavailable, match="missing_capabilities"):
        run_process(
            [sys.executable, str(script), "input"],
            timeout=2,
            helper=True,
            helper_capabilities=required,
        )
    assert not marker.exists()


def test_window_control_requires_postcondition_capability_before_dispatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from kyrin.desktop.platforms import gnome_window_control
    from kyrin.desktop.platforms.gnome_window_control import GnomeAppWindowController
    from kyrin.desktop.window_control import WindowControlStatus, WindowOperation

    calls = []

    def run(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(args[-1])
        return bus_reply("ControlAppWindow")

    monkeypatch.setattr(gnome_window_control, "run_process", run)
    controller = GnomeAppWindowController({"test": "test.desktop"})
    assert (
        controller.control("test", WindowOperation.MINIMIZE)
        is WindowControlStatus.UNKNOWN
    )
    assert calls == ["GetCapabilities"]
    assert controller.backend_status.reason == "missing_capabilities:GetAppWindowState"


@pytest.mark.parametrize("data", [None, {}, {"s": "value"}, "string", 5, []])
def test_malformed_bus_envelope_is_not_an_exception(data: object) -> None:
    from kyrin.backend_protocol import bus_status

    assert bus_status(data, {"GetActiveApp"}).reason == "malformed_handshake"


@pytest.mark.parametrize(
    "cause,reason",
    [
        (FileNotFoundError(), "transport_missing"),
        (PermissionError(), "access_denied"),
        (subprocess.TimeoutExpired("busctl", 0.5), "service_timeout"),
    ],
)
def test_probe_transport_failure_has_a_specific_reason(
    cause: Exception, reason: str
) -> None:
    from kyrin.backend_protocol import probe_gnome

    with patch("subprocess.run", side_effect=cause) as run:
        status = probe_gnome("ActiveApp", {"GetActiveApp"}, run=run, retry_delay_s=0)
        assert status.reason == reason
        assert run.call_count == (3 if reason == "service_timeout" else 1)
