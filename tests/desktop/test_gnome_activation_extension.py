"""Exercise the GNOME window-focus method without touching the live desktop."""

import shutil
import subprocess
from pathlib import Path

import pytest

_EXTENSION = (
    Path(__file__).resolve().parents[2]
    / "integrations/gnome-shell/active-app@kyrin.local/extension.js"
)

_HARNESS = """
class Extension {}
class WindowPicker {
    constructor(onSelect, onDismiss) {
        this.onSelect = onSelect;
        this.onDismiss = onDismiss;
    }
    show(_windows) { return true; }
    destroy() {}
}
let windows = 1;
let requests = 0;
let focus = null;
let lookedUp = [];
let maximized = false;
let fullscreen = false;
const window = {
    minimized: false,
    get_stable_sequence: () => 17,
    get_pid: () => 42,
    get_frame_rect: () => ({x: 100, y: 50, width: 1600, height: 900}),
    can_minimize: () => true,
    can_maximize: () => true,
    can_close: () => true,
    is_maximized: () => maximized,
    is_fullscreen: () => fullscreen,
    maximize: () => { maximized = true; },
    unmaximize: () => { maximized = false; },
    make_fullscreen: () => { fullscreen = true; },
    unmake_fullscreen: () => { fullscreen = false; },
    minimize: () => { window.minimized = true; },
    delete: timestamp => {
        if (timestamp !== 456) throw new Error('wrong close timestamp');
        windows = 0;
    },
};
const app = {
    get_name: () => 'Telegram',
    get_n_windows: () => windows,
    get_windows: () => windows === 2 ? [window, {}] : windows ? [window] : [],
};
const terminalFirst = {get_stable_sequence: () => 21};
const terminalSecond = {get_stable_sequence: () => 22};
let terminalWindows = [terminalFirst, terminalSecond];
const terminal = {get_name: () => 'Terminal', get_windows: () => terminalWindows};
const Main = {
    overview: {show: () => { requests++; }},
    activateWindow: (candidate, timestamp) => {
        if (![window, terminalFirst, terminalSecond].includes(candidate)
            || timestamp !== 456) throw new Error('wrong window');
        requests++;
        window.minimized = false;
        focus = candidate;
    },
};
const Shell = {
    AppSystem: {get_default: () => ({lookup_app: id => {
        lookedUp.push(id);
        return id === 'telegram.desktop' ? app
            : id === 'org.gnome.Ptyxis.desktop' ? terminal : null;
    }})},
    WindowTracker: {get_default: () => ({get_window_app: candidate =>
        candidate === window ? {get_id: () => 'telegram.desktop'} : null})},
};
let vanished = null;
let unwatchCount = 0;
class WindowCloseConfirmation {
    constructor(done) { this.done = done; this.finished = false; }
    show(observation, language) {
        this.observation = observation;
        this.language = language;
    }
    decide(approved) {
        if (!this.finished) { this.finished = true; this.done(approved); }
    }
    cancel() { this.decide(false); }
}
function invocation(replies) {
    return {get_connection: () => ({}), get_sender: () => ':test',
        return_value: value => replies.push(value.value[0])};
}
function prepareApproved(extension, appId, number) {
    const value = extension.PrepareWindowClose(appId, number);
    if (value) {
        const replies = [];
        extension.ConfirmWindowCloseAsync(
            [JSON.parse(value).generation, 'en'], invocation(replies));
        extension._closeDialog.decide(true);
        if (replies[0] !== 'approved') throw new Error('test confirmation failed');
    }
    return value;
}
const Gio = {
    BusNameWatcherFlags: {NONE: 0},
    bus_watch_name_on_connection: (_conn, _name, _flags, _appeared, gone) => {
        vanished = gone;
        return 1;
    },
    bus_unwatch_name: () => { unwatchCount++; vanished = null; },
    DBus: {session: {}}, DBusExportedObject: {
    wrapJSObject: () => ({export: () => {}, unexport: () => {}}),
}};
let clock = 1000000;
let generation = 0;
let focusChanged = () => {};
const GLib = {
    Variant: class { constructor(_type, value) { this.value = value; } },
    get_monotonic_time: () => clock,
    uuid_string_random: () => String(++generation),
};
const global = {display: {
    connect: (_signal, callback) => { focusChanged = callback; return 1; },
    disconnect: () => {},
    get_current_time_roundtrip: () => 456,
    get_focus_window: () => focus,
}, get_pointer: () => [500, 300, 0]};
"""

_CASES = """
const extension = new KyrinActiveAppExtension();
extension.enable();
if (extension.HasAppWindow('telegram.desktop') !== 'open'
    || extension.CountAppWindows('telegram.desktop') !== 1)
    throw new Error('window presence did not match the app');
if (extension.CountAppWindows('../telegram.desktop') !== -1)
    throw new Error('invalid window count was accepted');
if (extension.ShowAllWindows() !== 'requested' || requests !== 1)
    throw new Error('overview was not requested');
requests = 0;
if (extension.ActivateExistingApp('telegram.desktop') !== 'requested'
    || requests !== 1) throw new Error('existing window was not activated');
windows = 0;
if (extension.ActivateExistingApp('telegram.desktop') !== 'no_window'
    || requests !== 1) throw new Error('missing window was activated');
if (extension.ActivateExistingApp('../telegram.desktop') !== 'unknown'
    || lookedUp.length !== 4) throw new Error('invalid desktop ID was looked up');
windows = 2;
focus = null;
if (extension.ActivateExistingApp('telegram.desktop') !== 'multiple_windows')
    throw new Error('ambiguous activation was accepted');
focus = window;
if (extension.GetActiveWindowToken() !== '17')
    throw new Error('focused window token was incorrect');
if (JSON.stringify(extension.GetActiveWindowAndPointer()) !==
    JSON.stringify(['telegram.desktop', 42, 100, 50, 1600, 900, 500, 300]))
    throw new Error('focused window geometry or pointer was incorrect');
if (extension.ActivateExistingApp('telegram.desktop') !== 'requested')
    throw new Error('focused app window was not selected');
windows = 1;
if (extension.ControlAppWindow('telegram.desktop', 'minimize')[0] !== 'requested'
    || !JSON.parse(extension.GetAppWindowState('telegram.desktop', '17')).minimized)
    throw new Error('window was not minimized');
if (extension.ControlAppWindow('telegram.desktop', 'restore')[0] !== 'requested'
    || !JSON.parse(extension.GetAppWindowState('telegram.desktop', '17')).focused)
    throw new Error('window was not restored');
if (extension.ControlAppWindow('telegram.desktop', 'maximize')[0] !== 'requested'
    || !JSON.parse(extension.GetAppWindowState('telegram.desktop', '17')).maximized)
    throw new Error('window was not maximized');
if (extension.ControlAppWindow('telegram.desktop', 'fullscreen')[0] !== 'requested'
    || !JSON.parse(extension.GetAppWindowState('telegram.desktop', '17')).fullscreen)
    throw new Error('window was not fullscreen');
if (extension.ControlAppWindow('telegram.desktop', 'unmaximize')[0] !== 'requested'
    || JSON.parse(extension.GetAppWindowState('telegram.desktop', '17')).maximized
    || JSON.parse(extension.GetAppWindowState('telegram.desktop', '17')).fullscreen)
    throw new Error('window did not return to normal size');
if (extension.ControlAppWindow('telegram.desktop', 'fullscreen')[0] !== 'requested'
    || extension.ControlAppWindow('telegram.desktop', 'unfullscreen')[0] !== 'requested'
    || JSON.parse(extension.GetAppWindowState('telegram.desktop', '17')).fullscreen)
    throw new Error('window did not exit fullscreen');
windows = 2;
focus = null;
if (extension.PrepareWindowClose('telegram.desktop', 0) !== '')
    throw new Error('ambiguous close was accepted');
focus = window;
const close = JSON.parse(extension.PrepareWindowClose('telegram.desktop', 0));
if (extension.CloseConfirmedWindow(close.generation) !== 'requested'
    || extension.GetAppWindowState('telegram.desktop', '17') !== 'no_window')
    throw new Error('window was not closed');
if (extension.PrepareWindowClose('../telegram.desktop', 0) !== '')
    throw new Error('invalid app was controlled');
if (extension.ShowAppWindows('telegram.desktop') !== 'unknown')
    throw new Error('unrelated app was shown');
if (extension.ShowAppWindows('org.gnome.Ptyxis.desktop') !== 'requested')
    throw new Error('terminal picker was not shown');
if (extension.ActivateShownAppWindow('org.gnome.Ptyxis.desktop', 0) !== 'stale')
    throw new Error('invalid window number was accepted');
terminalWindows = [terminalSecond];
if (extension.ActivateShownAppWindow('org.gnome.Ptyxis.desktop', 1) !== 'stale')
    throw new Error('closed window was replaced with another window');
terminalWindows = [terminalFirst, terminalSecond];
if (extension.ShowAppWindows('org.gnome.Ptyxis.desktop') !== 'requested')
    throw new Error('terminal picker could not be reopened');
if (extension.ActivateShownAppWindow('org.gnome.Ptyxis.desktop', 2) !== 'requested'
    || focus !== terminalSecond)
    throw new Error('wrong terminal window was activated');
windows = 1;
if (extension.ShowOpenWindows(['../telegram.desktop']) !== 'unknown')
    throw new Error('invalid ID was accepted by global picker');
if (extension.ShowOpenWindows(
    ['telegram.desktop', 'org.gnome.Ptyxis.desktop']) !== 'requested')
    throw new Error('global picker was not shown');
if (extension.ActivateShownOpenApp('org.gnome.Ptyxis.desktop') !== 'ambiguous')
    throw new Error('ambiguous app name was activated');
if (extension.ActivateShownOpenApp('telegram.desktop') !== 'requested'
    || focus !== window)
    throw new Error('unique app window was not activated');
if (extension.ShowOpenWindows(
    ['telegram.desktop', 'org.gnome.Ptyxis.desktop']) !== 'requested')
    throw new Error('global picker could not be reopened');
terminalWindows = [terminalSecond];
if (extension.ActivateShownOpenWindow(2) !== 'stale')
    throw new Error('stale global window activated another window');
if (extension.ShowOpenWindows(['telegram.desktop']) !== 'requested'
    || extension.HideOpenWindows() !== 'requested'
    || extension.ActivateShownOpenWindow(1) !== 'not_shown')
    throw new Error('global picker cancel did not clear the snapshot');
extension.disable();
print('GNOME existing-window activation: passed');
"""


def test_extension_activates_only_an_existing_registered_window() -> None:
    gjs = shutil.which("gjs")
    if gjs is None:
        pytest.skip("GJS is not installed")
    source = "\n".join(
        line
        for line in _EXTENSION.read_text(encoding="utf-8").splitlines()
        if not line.startswith("import ")
    ).replace(
        "export default class KyrinActiveAppExtension",
        "globalThis.KyrinActiveAppExtension = class KyrinActiveAppExtension",
    )
    result = subprocess.run(
        [
            gjs,
            "-c",
            _HARNESS
            + source
            + _CASES.replace(
                "extension.PrepareWindowClose(", "prepareApproved(extension, "
            ),
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )
    assert result.returncode == 0, result.stderr
    assert "existing-window activation: passed" in result.stdout


_CLOSE_CASES = {
    "focus_round_trip": """
        const prepared = JSON.parse(
            extension.PrepareWindowClose('telegram.desktop', 0));
        focus = {};
        focusChanged();
        focus = window;
        if (extension.CloseConfirmedWindow(prepared.generation) !== 'stale'
            || windows !== 1)
            throw new Error('focus round trip revived an invalidated decision');
    """,
    "focus_changed": """
        const prepared = JSON.parse(
            extension.PrepareWindowClose('telegram.desktop', 0));
        focus = {};
        if (extension.CloseConfirmedWindow(prepared.generation) !== 'stale'
            || windows !== 1)
            throw new Error('switched focus consumed confirmation');
        focus = window;
        if (extension.CloseConfirmedWindow(prepared.generation) !== 'stale')
            throw new Error('bad consumption did not burn confirmation');
    """,
    "same_pid_replacement": """
        const prepared = JSON.parse(
            extension.PrepareWindowClose('telegram.desktop', 0));
        const replacement = {...window, get_stable_sequence: () => 18};
        app.get_windows = () => [replacement];
        if (extension.CloseConfirmedWindow(prepared.generation) !== 'stale'
            || windows !== 1)
            throw new Error('replacement window consumed confirmation');
    """,
    "expiry": """
        const prepared = JSON.parse(
            extension.PrepareWindowClose('telegram.desktop', 0));
        clock += 10000000;
        if (extension.CloseConfirmedWindow(prepared.generation) !== 'stale'
            || windows !== 1)
            throw new Error('expired confirmation closed a window');
    """,
    "expiry_before_dispatch": """
        const prepared = JSON.parse(
            extension.PrepareWindowClose('telegram.desktop', 0));
        global.display.get_current_time_roundtrip = () => {
            clock += 10000000;
            return 456;
        };
        if (extension.CloseConfirmedWindow(prepared.generation) !== 'stale'
            || windows !== 1)
            throw new Error('expiry during timestamp read still sent close');
    """,
    "old_generation": """
        const old = JSON.parse(extension.PrepareWindowClose('telegram.desktop', 0));
        const fresh = JSON.parse(extension.PrepareWindowClose('telegram.desktop', 0));
        if (extension.CloseConfirmedWindow(old.generation) !== 'stale'
            || windows !== 1)
            throw new Error('old dialog consumed a fresh request');
        if (extension.CloseConfirmedWindow(fresh.generation) !== 'stale')
            throw new Error('mismatched consumption did not burn confirmation');
    """,
    "save_dialog_and_replay": """
        let saveDialog = false;
        let closes = 0;
        window.delete = () => { closes++; saveDialog = true; };
        const prepared = JSON.parse(
            extension.PrepareWindowClose('telegram.desktop', 0));
        if (extension.CloseConfirmedWindow(prepared.generation) !== 'requested'
            || !saveDialog || windows !== 1 || closes !== 1)
            throw new Error('normal application close/save dialog was bypassed');
        if (extension.CloseConfirmedWindow(prepared.generation) !== 'stale'
            || closes !== 1)
            throw new Error('confirmation was reused');
    """,
    "picker_replaced": """
        extension.ShowOpenWindows(['telegram.desktop']);
        const prepared = JSON.parse(extension.PrepareWindowClose('', 1));
        if (extension._picker !== null)
            throw new Error('Shell modal grab was retained');
        extension.ShowOpenWindows(['telegram.desktop']);
        if (extension.CloseConfirmedWindow(prepared.generation) !== 'stale'
            || windows !== 1)
            throw new Error('new picker consumed old close decision');
    """,
    "terminal_numbered": """
        Object.assign(terminalSecond, {get_pid: () => 99, can_close: () => true});
        let closed = 0;
        terminalSecond.delete = () => { closed++; };
        extension.ShowAppWindows('org.gnome.Ptyxis.desktop');
        const prepared = JSON.parse(
            extension.PrepareWindowClose('org.gnome.Ptyxis.desktop', 2));
        if (prepared.window_token !== '22' || prepared.process_id !== 99
            || closed !== 0)
            throw new Error('numbered terminal target was not observed before close');
        if (extension.CloseConfirmedWindow(prepared.generation) !== 'requested'
            || closed !== 1)
            throw new Error('confirmed terminal window did not close normally');
    """,
    "legacy_bypass": """
        extension.ShowOpenWindows(['telegram.desktop']);
        if (extension.ControlAppWindow('telegram.desktop', 'close')[0] !==
                'confirmation_required'
            || extension.CloseShownOpenWindow(1, ['telegram.desktop']) !==
                'confirmation_required'
            || extension.CloseShownAppWindow('org.gnome.Ptyxis.desktop', 1) !==
                'confirmation_required'
            || windows !== 1)
            throw new Error('legacy API bypassed confirmation');
    """,
}


@pytest.mark.parametrize("case", _CLOSE_CASES)
@pytest.mark.parametrize("persistent", [False, True])
def test_extension_close_is_atomic_bound_and_single_use(
    case: str, persistent: bool
) -> None:
    gjs = shutil.which("gjs")
    if gjs is None:
        pytest.skip("GJS is not installed")
    source = "\n".join(
        line
        for line in _EXTENSION.read_text(encoding="utf-8").splitlines()
        if not line.startswith("import ")
    ).replace(
        "export default class KyrinActiveAppExtension",
        "globalThis.KyrinActiveAppExtension = class KyrinActiveAppExtension",
    )
    result = subprocess.run(
        [
            gjs,
            "-c",
            _HARNESS
            + source
            + """
        const extension = new KyrinActiveAppExtension();
        extension.enable();
        """
            + (
                _CLOSE_CASES[case].replace(
                    "CloseConfirmedWindow", "CloseAuthorizedWindow"
                )
                if persistent
                else _CLOSE_CASES[case].replace(
                    "extension.PrepareWindowClose(", "prepareApproved(extension, "
                )
            )
            + "\nprint('bound close passed');",
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize(
    "change",
    ["approve", "cancel", "expiry", "focus", "caller_gone", "disable", "replace"],
)
def test_native_confirmation_lifetime(change: str) -> None:
    gjs = shutil.which("gjs")
    if gjs is None:
        pytest.skip("GJS is not installed")
    source = "\n".join(
        line
        for line in _EXTENSION.read_text().splitlines()
        if not line.startswith("import ")
    ).replace("export default class", "class")
    body = """
        const extension = new KyrinActiveAppExtension();
        extension.enable();
        focus = window;
        const prepared = JSON.parse(
            extension.PrepareWindowClose('telegram.desktop', 0));
        const replies = [];
        extension.ConfirmWindowCloseAsync(
            [prepared.generation, 'fa'], invocation(replies));
        const dialog = extension._closeDialog;
        if (!dialog || replies.length || windows !== 1 || dialog.language !== 'fa')
            throw new Error('confirmation did not wait for explicit consent');
        if (dialog.observation.deadline !== prepared.deadline)
            throw new Error('confirmation extended original deadline');
        CHANGE
        dialog.decide(true); // A late click cannot revive a completed decision.
        if (replies.length !== 1 || replies[0] !== EXPECTED || unwatchCount !== 1)
            throw new Error('confirmation lifetime was not single-use');
        const result = extension.CloseConfirmedWindow(prepared.generation);
        if (result !== RESULT || windows !== WINDOWS)
            throw new Error('invalid confirmation changed a window');
        if (extension.CloseConfirmedWindow(prepared.generation) !== 'stale')
            throw new Error('confirmation replayed');
    """
    changes = {
        "approve": "dialog.decide(true);",
        "cancel": "dialog.cancel();",
        "expiry": "clock += 10000000; dialog.decide(true);",
        "focus": "focus = {}; focusChanged(); focus = window;",
        "caller_gone": "vanished();",
        "disable": "extension.disable();",
        "replace": "extension.PrepareWindowClose('telegram.desktop', 0);",
    }
    body = body.replace("CHANGE", changes[change])
    body = body.replace(
        "EXPECTED", "'approved'" if change == "approve" else "'declined'"
    )
    body = body.replace("RESULT", "'requested'" if change == "approve" else "'stale'")
    body = body.replace("WINDOWS", "0" if change == "approve" else "1")
    result = subprocess.run(
        [gjs, "-c", _HARNESS + source + body],
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )
    assert result.returncode == 0, result.stderr


def test_extension_refuses_close_without_native_consent() -> None:
    gjs = shutil.which("gjs")
    if gjs is None:
        pytest.skip("GJS is not installed")
    source = "\n".join(
        line
        for line in _EXTENSION.read_text().splitlines()
        if not line.startswith("import ")
    ).replace("export default class", "class")
    result = subprocess.run(
        [
            gjs,
            "-c",
            _HARNESS
            + source
            + """
        const extension = new KyrinActiveAppExtension();
        extension.enable();
        const prepared = JSON.parse(
            extension.PrepareWindowClose('telegram.desktop', 0));
        const status = extension.CloseConfirmedWindow(prepared.generation);
        if (status !== 'confirmation_required' || windows !== 1)
            throw new Error('close bypassed native consent');
        """,
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )
    assert result.returncode == 0, result.stderr
