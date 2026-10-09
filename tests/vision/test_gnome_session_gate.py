"""Exercise the extension's permission gate without a desktop session."""

import shutil
import subprocess
from pathlib import Path

import pytest

_EXTENSION = (
    Path(__file__).resolve().parents[2]
    / "integrations/gnome-shell/window-capture-prototype@kyrin.local/extension.js"
)

_FAKES = r"""
class Extension {}
let owner = ':1.42';
let dialogs = [];
let ownerChanged = null;
let screenshotCount = 0;
let deferOwner = false;
let pendingOwnerCheck = null;
const window = {get_pid: () => 123};
let signals = new Map();
let nextId = 1;
const global = {display: {
    get_focus_window: () => window,
    connect: (_name, callback) => {
        let id = nextId++;
        signals.set(id, callback);
        return id;
    },
    disconnect: id => signals.delete(id),
}};
const Gio = {
    DBusSignalFlags: {NONE: 0}, DBusCallFlags: {NONE: 0},
    DBus: {session: {
        signal_subscribe: (_a, _b, _c, _d, _e, _f, callback) => {
            ownerChanged = callback; return 1;
        },
        signal_unsubscribe: () => {},
        call: (_a, _b, _c, _d, _e, _f, _g, _h, _i, callback) => {
            const complete = () => callback(
                {call_finish: () => ({
                    unpack: () => [{}],
                    deepUnpack: () => [owner],
                })}, {});
            if (deferOwner)
                pendingOwnerCheck = complete;
            else
                complete();
        },
    }},
    DBusExportedObject: {wrapJSObject: () => ({export: () => {}, unexport: () => {}})},
    MemoryOutputStream: {new_resizable: () => ({
        close: () => {},
        steal_as_bytes: () => ({get_data: () => new Uint8Array([137,80,78,71])}),
    })},
};
const GLib = {
    Variant: class {constructor(_type, values) {this.values = values;}},
    VariantType: class {},
    PRIORITY_DEFAULT: 0, SOURCE_REMOVE: false,
    timeout_add: () => nextId++, source_remove: () => {},
};
const Shell = {
    WindowTracker: {get_default: () => ({get_window_app: () => ({
        is_window_backed: () => false, get_id: () => 'test.desktop',
    })})},
    Screenshot: class {
        screenshot_window(_frame, _cursor, _stream, callback) {
            screenshotCount++; callback(this, {});
        }
        screenshot_window_finish() {return true;}
    },
};
const St = {Label: class {}};
const ModalDialog = {ModalDialog: class {
    constructor() {this.contentLayout = {add_child: () => {}}; dialogs.push(this);}
    setButtons(buttons) {this.buttons = buttons;}
    connect(_signal, callback) {this.onClosed = callback;}
    open() {return true;}
    close() {this.onClosed?.();}
}};
function request(extension, member, sender) {
    const invocation = {
        get_sender: () => sender,
        return_value: reply => {invocation.reply = reply;},
    };
    extension[member + 'Async']([], invocation);
    return invocation;
}
function check(condition, message) {if (!condition) throw new Error(message);}
"""

_CASES = r"""
const extension = new KyrinWindowCapturePrototype();
extension.enable();
let foreignGrant = request(extension, 'RequestSession', ':1.99');
check(foreignGrant.reply.values[0] === false && dialogs.length === 0,
    'foreign requester opened permission dialog');
let before = request(extension, 'CaptureActiveWindow', ':1.42');
check(before.reply.values[0] === '' && screenshotCount === 0,
    'captured before permission');
let grant = request(extension, 'RequestSession', ':1.42');
check(!grant.reply && dialogs.length === 1, 'permission dialog missing');
let duplicate = request(extension, 'RequestSession', ':1.42');
check(duplicate.reply.values[0] === false, 'concurrent request accepted');
dialogs.at(-1).buttons[0].action();
check(grant.reply.values[0] === false, 'denied session granted');
grant = request(extension, 'RequestSession', ':1.42');
dialogs.at(-1).buttons[1].action();
check(grant.reply.values[0] === true, 'approved session denied');
let foreignCapture = request(extension, 'CaptureActiveWindow', ':1.99');
check(foreignCapture.reply.values[0] === '' && screenshotCount === 0,
    'foreign requester captured');
let captured = request(extension, 'CaptureActiveWindow', ':1.42');
check(captured.reply.values[0] === 'test.desktop' && screenshotCount === 1,
    'authorized requester could not capture');
let revoke = request(extension, 'RevokeSession', ':1.42');
check(revoke.reply.values[0] === true, 'revoke failed');
captured = request(extension, 'CaptureActiveWindow', ':1.42');
check(captured.reply.values[0] === '' && screenshotCount === 1,
    'captured after revocation');
grant = request(extension, 'RequestSession', ':1.42');
dialogs.at(-1).buttons[1].action();
ownerChanged(null, null, null, null, null,
    {unpack: () => [{}, {}, {}],
     deepUnpack: () => ['org.kyrin.Desktop', ':1.42', '']});
captured = request(extension, 'CaptureActiveWindow', ':1.42');
check(captured.reply.values[0] === '' && screenshotCount === 1,
    'captured after bus owner disappeared');
owner = ':1.42';
grant = request(extension, 'RequestSession', ':1.42');
deferOwner = true;
dialogs.at(-1).buttons[1].action();
revoke = request(extension, 'RevokeSession', ':1.42');
check(revoke.reply.values[0] === true && grant.reply.values[0] === false,
    'revoke during owner check did not deny');
pendingOwnerCheck();
check(grant.reply.values[0] === false, 'late owner reply re-granted permission');
captured = request(extension, 'CaptureActiveWindow', ':1.42');
check(captured.reply.values[0] === '' && screenshotCount === 1,
    'captured after race-time revocation');
extension.disable();
print('GNOME session permission gate: passed');
"""


def test_gnome_extension_requires_the_app_owned_session() -> None:
    gjs = shutil.which("gjs")
    if gjs is None:
        pytest.skip("GJS is not installed")
    source = "\n".join(
        line for line in _EXTENSION.read_text(encoding="utf-8").splitlines()
        if not line.startswith("import ")
    ).replace(
        "export default class KyrinWindowCapturePrototype",
        "globalThis.KyrinWindowCapturePrototype = class KyrinWindowCapturePrototype",
    )
    result = subprocess.run(
        [gjs, "-c", _FAKES + source + _CASES],
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )
    assert result.returncode == 0, result.stderr
    assert "permission gate: passed" in result.stdout
