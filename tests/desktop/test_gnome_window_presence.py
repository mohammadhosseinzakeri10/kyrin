"""The GNOME window probe is read-only and fails closed on uncertain replies."""

import json
import subprocess

import pytest

from kyrin.desktop.platforms.gnome_window_presence import GnomeAppWindowPresence
from kyrin.desktop.window_presence import WindowPresence
from tests.desktop.test_backend_protocol import bus_reply


def test_window_probe_uses_only_a_bound_desktop_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[list[str]] = []

    def run(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(args)
        if args[-1] == "GetCapabilities":
            return bus_reply("HasAppWindow")
        return subprocess.CompletedProcess(
            args, 0, json.dumps({"type": "s", "data": ["open"]}), ""
        )

    monkeypatch.setattr(subprocess, "run", run)
    probe = GnomeAppWindowPresence({"terminal": "org.gnome.Ptyxis.desktop"})
    assert probe.observe("terminal") is WindowPresence.OPEN
    assert probe.observe("unbound") is WindowPresence.UNKNOWN
    assert len(calls) == 2
    assert calls[1][-2:] == ["s", "org.gnome.Ptyxis.desktop"]


def test_window_probe_treats_bad_bus_reply_as_unknown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def run(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        if args[-1] == "GetCapabilities":
            return bus_reply("HasAppWindow")
        return subprocess.CompletedProcess(args, 0, '{"data":["surprise"]}', "")

    monkeypatch.setattr(subprocess, "run", run)
    probe = GnomeAppWindowPresence({"terminal": "org.gnome.Ptyxis.desktop"})
    assert probe.observe("terminal") is WindowPresence.UNKNOWN


def test_window_count_is_fresh_and_validated(monkeypatch: pytest.MonkeyPatch) -> None:
    replies = iter(
        (
            '{"type":"i","data":[2]}',
            '{"type":"i","data":[-1]}',
            '{"type":"s","data":["2"]}',
        )
    )

    def run(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        if args[-1] == "GetCapabilities":
            return bus_reply("CountAppWindows")
        assert args[-3] == "CountAppWindows"
        return subprocess.CompletedProcess(args, 0, next(replies), "")

    monkeypatch.setattr(subprocess, "run", run)
    probe = GnomeAppWindowPresence({"terminal": "org.gnome.Ptyxis.desktop"})
    assert probe.count("terminal") == 2
    assert probe.count("terminal") is None
    assert probe.count("terminal") is None
    assert probe.count("unbound") is None
