"""Owner diagnostic transport never turns errors into empty successful scans."""

import subprocess

import pytest

from scripts.actions.inspect_visible_controls import inspect_controls


@pytest.mark.parametrize(
    "stdout,returncode,status",
    [
        ("[]", 0, "invalid_helper_reply"),
        ("invalid", 0, "invalid_helper_reply"),
        ("", 1, "helper_error"),
        ('{"status":"scan_rejected"}', 0, "scan_rejected"),
    ],
)
def test_diagnostic_transport_sanitizes_errors(
    monkeypatch: pytest.MonkeyPatch,
    stdout: str,
    returncode: int,
    status: str,
) -> None:
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda args, **_kw: subprocess.CompletedProcess(
            args, returncode, stdout, "private stderr"
        ),
    )
    report = inspect_controls([])
    assert report["status"] == status
    assert "private" not in str(report)


@pytest.mark.parametrize("timeout", [True, False])
def test_diagnostic_transport_has_finite_timeout(
    monkeypatch: pytest.MonkeyPatch,
    timeout: bool,
) -> None:
    def run(args: list[str], **kwargs: object) -> None:
        assert kwargs["timeout"] == 8
        assert "--diagnose-current" in args
        if timeout:
            raise subprocess.TimeoutExpired(args, 8)
        raise FileNotFoundError("unavailable")

    monkeypatch.setattr(subprocess, "run", run)
    assert inspect_controls([])["status"] == (
        "helper_timeout" if timeout else "helper_unavailable"
    )


@pytest.mark.parametrize("include_geometry", [False, True])
def test_window_geometry_requires_explicit_diagnostic_option(
    monkeypatch: pytest.MonkeyPatch,
    include_geometry: bool,
) -> None:
    def run(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        assert args[2] == (
            "--diagnose-current-geometry" if include_geometry else "--diagnose-current"
        )
        assert kwargs["timeout"] == 8
        assert args[3] == "[]"
        return subprocess.CompletedProcess(
            args,
            0,
            '{"status":"scan_rejected","reason_code":"window_bounds_mismatch"}',
            "private stderr",
        )

    monkeypatch.setattr(subprocess, "run", run)
    report = inspect_controls([], include_geometry=include_geometry)
    assert report["reason_code"] == "window_bounds_mismatch"
    assert "private" not in str(report)


def test_geometry_cli_requests_only_read_only_diagnostic(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    import json
    import sys

    from scripts.actions import inspect_visible_controls as diagnostic

    monkeypatch.setattr(
        sys, "argv", ["inspect_visible_controls", "--geometry", "--delay", "0"]
    )
    monkeypatch.setattr(diagnostic, "sleep", lambda delay: None)

    def inspect(labels: list[str], *, include_geometry: bool) -> dict[str, object]:
        assert labels == [] and include_geometry
        return {"status": "scan_rejected", "geometry": {"fits_focused_frame": False}}

    monkeypatch.setattr(diagnostic, "inspect_controls", inspect)
    assert diagnostic.main() == 1
    report = json.loads(capsys.readouterr().out)
    assert report["geometry"]["fits_focused_frame"] is False
