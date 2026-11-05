"""Actual Shell tab-picker methods, using inert windows and no native session."""

import shutil
import subprocess
from pathlib import Path

import pytest

SOURCE = (
    Path(__file__).resolve().parents[2]
    / "integrations/gnome-shell/active-app@kyrin.local/extension.js"
)


@pytest.mark.parametrize(
    "case",
    [
        "valid",
        "one",
        "generation",
        "expired",
        "pid",
        "token",
        "removed",
        "added",
        "cancel",
        "wrong_app",
        "number",
    ],
)
def test_tab_choice_is_one_use_and_binds_original_window(case: str) -> None:
    gjs = shutil.which("gjs")
    assert gjs is not None
    source = "\n".join(
        line
        for line in SOURCE.read_text().splitlines()
        if not line.startswith("import ")
    ).replace("export default class", "class")
    setup = {
        "generation": "wanted = 'b'.repeat(32);",
        "expired": "now += 31 * 1000000;",
        "pid": "pid = 99;",
        "token": "token = 99;",
        "removed": "current.pop();",
        "added": "current.push(windows[0]);",
        "cancel": "e._clearPicker();",
        "wrong_app": "app = 'other.desktop';",
        "number": "number = 99;",
    }.get(case, "")
    harness = """
const Extension = class {};
let now = 1000000, pid = 5, token = 1, activated = [];
const windows = [0,1].map(i => ({get_pid: () => pid,
    get_stable_sequence: () => i === 0 ? token : 2}));
let current = CASE === 'one' ? [windows[0]] : [...windows];
const Shell = {AppSystem: {get_default: () => ({lookup_app: id =>
    id === 'org.gnome.Ptyxis.desktop' ? {get_windows: () => current} : null})}};
const Main = {activateWindow: w => activated.push(w)};
const global = {display: {get_current_time_roundtrip: () => 9}};
const GLib = {get_monotonic_time: () => now};
const WindowPicker = class {show() {return true;} destroy() {}};
""".replace("CASE", repr(case))
    body = """
const e = new KyrinActiveAppExtension();
let app = 'org.gnome.Ptyxis.desktop', wanted = 'a'.repeat(32), number = 1;
const shown = JSON.parse(e.ShowAppWindowsForTab(app, wanted));
if (shown.status !== 'requested' || shown.count !== current.length || activated.length)
    throw new Error('show changed focus or lost membership');
SETUP
const reply = JSON.parse(e.ActivateAppWindowForTab(app, wanted, number));
if (CASE === 'valid' || CASE === 'one') {
    if (reply.status !== 'requested' || reply.window_token !== '1' ||
        reply.process_id !== 5 || activated[0] !== windows[0])
        throw new Error('selected another window or lost binding');
} else if (reply.status === 'requested' || activated.length) {
    throw new Error('invalid choice activated a window');
}
const count = activated.length;
if (JSON.parse(e.ActivateAppWindowForTab(app, wanted, number)).status === 'requested' ||
    activated.length !== count) throw new Error('replayed choice');
print('passed');
""".replace("CASE", repr(case)).replace("SETUP", setup)
    result = subprocess.run(
        [gjs, "-c", harness + source + body],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert result.returncode == 0, result.stderr
