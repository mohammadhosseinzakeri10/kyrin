"""Execute the actual Shell methods with inert window objects and modal UI."""

import shutil
import subprocess
from pathlib import Path

import pytest

SOURCE = (
    Path(__file__).resolve().parents[2]
    / "integrations/gnome-shell/active-app@kyrin.local/extension.js"
)
HARNESS = """
let now = 1000000, generation = 0, focus = {}, dialog = null;
let pid = 42, token = 1, closable = true, throwSecond = false;
const closed = [], replies = [];
const windows = [0, 1].map(index => ({
    get_stable_sequence: () => index === 0 ? token : 2,
    get_pid: () => pid,
    can_close: () => closable,
    delete: () => {
        if (throwSecond && index === 1) throw new Error('native refusal');
        closed.push(index + 1);
    },
}));
let current = [...windows];
const Extension = class {};
const Main = {};
const global = {display: {
    get_focus_window: () => focus,
    get_current_time_roundtrip: () => 9,
}};
const Shell = {AppSystem: {get_default: () => ({
    lookup_app: id => id === 'test.desktop' ? {get_windows: () => current} : null,
})}};
const GLib = {
    get_monotonic_time: () => now,
    uuid_string_random: () => String(++generation),
    Variant: class { constructor(_type, value) { this.value = value; } },
};
const Gio = {
    BusNameWatcherFlags: {NONE: 0},
    bus_watch_name_on_connection: () => 1,
    bus_unwatch_name: () => {},
};
const WindowCloseConfirmation = class {
    constructor(done) { this.done = done; this.finished = false; dialog = this; }
    show(observation) { this.observation = observation; }
    finish(approved) {
        if (this.finished) return;
        this.finished = true; this.done(approved);
    }
    cancel() { this.finish(false); }
};
const invocation = {
    get_connection: () => ({}), get_sender: () => ':test',
    return_value: variant => replies.push(variant.value[0]),
};
"""


@pytest.mark.parametrize(
    "case",
    [
        "approve",
        "decline",
        "expired",
        "new_window",
        "removed",
        "pid",
        "token",
        "focus",
        "unclosable",
        "wrong_generation",
        "unapproved",
        "cancelled",
        "partial",
    ],
)
def test_group_snapshot_confirmation_and_atomic_dispatch(case: str) -> None:
    gjs = shutil.which("gjs")
    assert gjs is not None
    source = "\n".join(
        line
        for line in SOURCE.read_text().splitlines()
        if not line.startswith("import ")
    ).replace("export default class", "class")
    setup = {
        "expired": "now = 11000000;",
        "new_window": "current.push(windows[0]);",
        "removed": "current.pop();",
        "pid": "pid = 99;",
        "token": "token = 7;",
        "focus": "focus = {};",
        "unclosable": "closable = false;",
        "wrong_generation": "wanted = 'other';",
        "cancelled": "e._clearPicker();",
        "partial": "throwSecond = true;",
    }.get(case, "")
    body = """
const e = new KyrinActiveAppExtension();
if (e.PrepareAppWindowsClose('unknown.desktop') !== '')
    throw new Error('unknown app accepted');
const observation = JSON.parse(e.PrepareAppWindowsClose('test.desktop'));
if (observation.windows.length !== 2 || closed.length)
    throw new Error('prepare acted or lost complete membership');
let wanted = observation.generation;
if (CASE !== 'unapproved') {
    e.ConfirmAppWindowsCloseAsync([wanted, 'en'], invocation);
    if (dialog.observation.windows.length !== 2)
        throw new Error('approval lacks group scope');
    dialog.finish(CASE !== 'decline');
}
SETUP
const result = e.CloseConfirmedAppWindows(wanted);
if (CASE === 'approve') {
    if (result !== 'requested' || closed.join(',') !== '1,2')
        throw new Error('exact group not closed');
} else if (CASE === 'partial') {
    if (result !== 'partial' || closed.join(',') !== '1')
        throw new Error('partial dispatch misreported');
} else if (closed.length || result === 'requested') {
    throw new Error('invalid group or decision executed');
}
const count = closed.length;
if (e.CloseConfirmedAppWindows(wanted) === 'requested' || closed.length !== count)
    throw new Error('replayed group approval');
print('group close: passed');
""".replace("CASE", repr(case)).replace("SETUP", setup)
    result = subprocess.run(
        [gjs, "-c", HARNESS + source + body],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("case", [
    "saved", "expired", "new_window", "pid", "token", "focus", "cancelled",
    "wrong_generation", "partial",
])
def test_saved_group_close_preserves_atomic_snapshot_without_dialog(case: str) -> None:
    gjs = shutil.which("gjs")
    assert gjs is not None
    source = "\n".join(line for line in SOURCE.read_text().splitlines()
                       if not line.startswith("import ")).replace(
                           "export default class", "class")
    setup = {
        "expired": "now = 11000000;", "new_window": "current.push(windows[0]);",
        "pid": "pid = 99;", "token": "token = 7;", "focus": "focus = {};",
        "cancelled": "e._clearPicker();", "wrong_generation": "wanted = 'other';",
        "partial": "throwSecond = true;",
    }.get(case, "")
    body = """
const e = new KyrinActiveAppExtension();
const observation = JSON.parse(e.PrepareAppWindowsClose('test.desktop'));
let wanted = observation.generation;
SETUP
const result = e.CloseAuthorizedAppWindows(wanted);
if (dialog !== null) throw new Error('saved grant opened a modal');
if (CASE === 'saved') {
    if (result !== 'requested' || closed.join(',') !== '1,2')
        throw new Error('saved consent did not close the exact group');
} else if (CASE === 'partial') {
    if (result !== 'partial' || closed.join(',') !== '1')
        throw new Error('partial saved close misreported');
} else if (closed.length || result === 'requested') {
    throw new Error('saved consent bypassed identity/focus/deadline');
}
const count = closed.length;
if (e.CloseAuthorizedAppWindows(wanted) === 'requested' || closed.length !== count)
    throw new Error('saved commit replayed');
print('saved group close: passed');
""".replace("SETUP", setup).replace("CASE", repr(case))
    result = subprocess.run([gjs, "-c", HARNESS + source + body],
                            capture_output=True, text=True, timeout=10, check=False)
    assert result.returncode == 0, result.stderr
