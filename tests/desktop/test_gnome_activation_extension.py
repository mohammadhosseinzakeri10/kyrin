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
const Gio = {DBus: {session: {}}, DBusExportedObject: {
    wrapJSObject: () => ({export: () => {}, unexport: () => {}}),
}};
const global = {display: {
    get_current_time_roundtrip: () => 456,
    get_focus_window: () => focus,
}};
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
if (extension.ControlAppWindow('telegram.desktop', 'close')[0] !== 'multiple_windows')
    throw new Error('ambiguous close was accepted');
focus = window;
if (extension.ControlAppWindow('telegram.desktop', 'close')[0] !== 'requested'
    || extension.GetAppWindowState('telegram.desktop', '17') !== 'no_window')
    throw new Error('window was not closed');
if (extension.ControlAppWindow('../telegram.desktop', 'close')[0] !== 'unknown')
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
        [gjs, "-c", _HARNESS + source + _CASES],
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )
    assert result.returncode == 0, result.stderr
    assert "existing-window activation: passed" in result.stdout
