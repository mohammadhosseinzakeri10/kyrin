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
let screenshotIncludedFrame = false;
let deferOwner = false;
let pendingOwnerCheck = null;
let files = new Map();
let imageBytes = new Uint8Array([
    137,80,78,71,13,10,26,10,0,0,0,13,73,72,68,82,
    0,0,3,28,0,0,2,58,
]);
let monotonicUs = 100000000;
const window = {
    get_pid: () => 123,
    get_frame_rect: () => ({x: 10, y: 20, width: 800, height: 600}),
    get_monitor: () => 1,
    get_stable_sequence: () => 7,
};
let signals = new Map();
let nextId = 1;
const global = {display: {
    get_focus_window: () => window,
    get_monitor_scale: () => 1,
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
        steal_as_bytes: () => ({get_data: () => imageBytes}),
    })},
};
const GLib = {
    Variant: class {constructor(_type, values) {this.values = values;}},
    VariantType: class {},
    PRIORITY_DEFAULT: 0, SOURCE_REMOVE: false,
    timeout_add: () => nextId++, source_remove: () => {},
    uuid_string_random: () => 'capture-1',
    get_monotonic_time: () => monotonicUs,
    get_user_data_dir: () => '/tmp/kyrin-gjs-test',
    build_filenamev: parts => parts.join('/'),
    path_get_dirname: path => path.slice(0, path.lastIndexOf('/')),
    ChecksumType: {SHA256: 1},
    compute_checksum_for_string: (_type, value) => `hash:${value}`,
    file_get_contents: path => {
        if (!files.has(path)) throw new Error('missing file');
        return [true, new TextEncoder().encode(files.get(path))];
    },
    file_set_contents: (path, value) => {files.set(path, value); return true;},
    mkdir_with_parents: () => 0,
    chmod: () => 0,
    unlink: path => {if (!files.delete(path)) throw new Error('missing file');},
    FileTest: {EXISTS: 1},
    file_test: path => files.has(path),
};
const Shell = {
    WindowTracker: {get_default: () => ({get_window_app: () => ({
        is_window_backed: () => false, get_id: () => 'test.desktop',
    })})},
    Screenshot: class {
        screenshot_window(frame, _cursor, _stream, callback) {
            screenshotIncludedFrame = frame;
            screenshotCount++; callback(this, {});
        }
        screenshot_window_finish() {
            return [true, {x: 12, y: 48, width: 796, height: 570}];
        }
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
function requestPersistent(extension, sender, token) {
    const invocation = {
        get_sender: () => sender,
        return_value: reply => {invocation.reply = reply;},
    };
    extension.RequestPersistentSessionAsync([token], invocation);
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
check(screenshotIncludedFrame, 'captured window must include its frame');
check(captured.reply.values.slice(2, 10).join(',') ===
    '12,48,796,570,10,20,800,600', 'capture geometry was lost');
const geometry = JSON.parse(captured.reply.values[10]);
check(geometry.monitor_id === 1 && geometry.scale_x === 1 &&
    geometry.window_token === '7' && geometry.capture_id === 'capture-1' &&
    geometry.captured_at === 100 && geometry.padding.join(',') === '0,0,0,0',
    'explicit geometry was lost');
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
extension.enable();
deferOwner = false;
let persistent = requestPersistent(extension, ':1.42', 'a'.repeat(64));
check(!persistent.reply, 'first persistent request did not ask');
dialogs.at(-1).buttons[1].action();
check(persistent.reply.values[0] === true, 'persistent consent denied');
ownerChanged(null, null, null, null, null,
    {deepUnpack: () => ['org.kyrin.Desktop', ':1.42', '']});
owner = ':1.43';
const dialogCount = dialogs.length;
persistent = requestPersistent(extension, ':1.43', 'a'.repeat(64));
check(persistent.reply.values[0] === true, 'remembered permission not restored');
check(dialogs.length === dialogCount, 'restore unexpectedly asked again');
revoke = request(extension, 'RevokeSession', ':1.43');
check(revoke.reply.values[0] === true, 'remembered permission not revoked');
persistent = requestPersistent(extension, ':1.43', 'a'.repeat(64));
check(!persistent.reply, 'revoked permission restored');
dialogs.at(-1).buttons[0].action();
extension.disable();
print('GNOME session permission gate: passed');
"""

_VALIDATION_CASES = r"""
const extension = new KyrinWindowCapturePrototype();
extension.enable();
const grant = request(extension, 'RequestSession', ':1.42');
dialogs.at(-1).buttons[1].action();
check(grant.reply.values[0] === true, 'grant failed');
const captured = request(extension, 'CaptureActiveWindow', ':1.42');
const captureId = JSON.parse(captured.reply.values[10]).capture_id;
function validate() {
    const invocation = {
        get_sender: () => ':1.99',
        return_value: reply => {invocation.reply = reply;},
    };
    extension.ValidateCaptureAsync([captureId], invocation);
    return invocation.reply?.values[0];
}
check(validate() === true, 'unchanged capture was rejected');
const originalBytes = imageBytes;
imageBytes = new Uint8Array(imageBytes);
imageBytes[8] = 1;
check(validate() === false, 'changed content was accepted');
imageBytes = originalBytes;
monotonicUs += 11000000;
check(validate() === false, 'expired capture was accepted');
extension.disable();
print('GNOME capture validation: passed');
"""


def test_gnome_extension_requires_the_app_owned_session() -> None:
    gjs = shutil.which("gjs")
    if gjs is None:
        pytest.skip("GJS is not installed")
    source = "\n".join(
        line
        for line in _EXTENSION.read_text(encoding="utf-8").splitlines()
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


def test_gnome_capture_validation_rejects_changed_content() -> None:
    gjs = shutil.which("gjs")
    if gjs is None:
        pytest.skip("GJS is not installed")
    source = "\n".join(
        line
        for line in _EXTENSION.read_text(encoding="utf-8").splitlines()
        if not line.startswith("import ")
    ).replace(
        "export default class KyrinWindowCapturePrototype",
        "globalThis.KyrinWindowCapturePrototype = class KyrinWindowCapturePrototype",
    )
    result = subprocess.run(
        [gjs, "-c", _FAKES + source + _VALIDATION_CASES],
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )
    assert result.returncode == 0, result.stderr
    assert "capture validation: passed" in result.stdout
