"""The GNOME window probe is read-only and fails closed on uncertain replies."""

import json
import subprocess

from kyrin.desktop.platforms import gnome_window_presence
from kyrin.desktop.platforms.gnome_window_presence import GnomeAppWindowPresence
from kyrin.desktop.window_presence import WindowPresence


def test_window_probe_uses_only_a_bound_desktop_id(monkeypatch) -> None:
    calls: list[list[str]] = []

    def run(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(args)
        return subprocess.CompletedProcess(
            args, 0, json.dumps({"type": "s", "data": ["open"]}), ""
        )

    monkeypatch.setattr(gnome_window_presence.subprocess, "run", run)
    probe = GnomeAppWindowPresence({"terminal": "org.gnome.Ptyxis.desktop"})
    assert probe.observe("terminal") is WindowPresence.OPEN
    assert probe.observe("unbound") is WindowPresence.UNKNOWN
    assert len(calls) == 1
    assert calls[0][-2:] == ["s", "org.gnome.Ptyxis.desktop"]


def test_window_probe_treats_bad_bus_reply_as_unknown(monkeypatch) -> None:
    def run(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(args, 0, '{"data":["surprise"]}', "")

    monkeypatch.setattr(gnome_window_presence.subprocess, "run", run)
    probe = GnomeAppWindowPresence({"terminal": "org.gnome.Ptyxis.desktop"})
    assert probe.observe("terminal") is WindowPresence.UNKNOWN


def test_window_count_is_fresh_and_validated(monkeypatch) -> None:
    replies = iter(
        (
            '{"type":"i","data":[2]}',
            '{"type":"i","data":[-1]}',
            '{"type":"s","data":["2"]}',
        )
    )

    def run(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        assert args[-3] == "CountAppWindows"
        return subprocess.CompletedProcess(args, 0, next(replies), "")

    monkeypatch.setattr(gnome_window_presence.subprocess, "run", run)
    probe = GnomeAppWindowPresence({"terminal": "org.gnome.Ptyxis.desktop"})
    assert probe.count("terminal") == 2
    assert probe.count("terminal") is None
    assert probe.count("terminal") is None
    assert probe.count("unbound") is None
