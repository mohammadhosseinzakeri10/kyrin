"""Exercise the extension's permission gate without a desktop session."""

import json
import shutil
import struct
import subprocess
import zlib
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
    0,0,3,32,0,0,2,88,
]);
let monotonicUs = 100000000;
const window = {
    get_pid: () => 123,
    get_frame_rect: () => ({x: 10, y: 20, width: 800, height: 600}),
    get_monitor: () => 1,
    get_stable_sequence: () => 7,
    get_buffer_rect: () => window.get_frame_rect(),
    get_compositor_private: () => ({
        get_position: () => {
            const rect = window.get_buffer_rect(); return [rect.x, rect.y];
        },
        get_size: () => {
            const rect = window.get_buffer_rect(); return [rect.width, rect.height];
        },
    }),
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
            return [true, window.get_frame_rect()];
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
    '10,20,800,600,10,20,800,600', 'capture geometry was lost');
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


def _png(
    *,
    metadata: str = "first",
    first_pixel: bytes = b"\xff\x00\x00",
    last_pixel: bytes = b"\xff\x00\x00",
    width: int = 3,
    alpha: bool = False,
    opacity: int = 255,
    compression: int = 6,
) -> list[int]:
    """Valid in-memory PNGs, including odd-width RGB rows with padding."""

    def chunk(kind: bytes, data: bytes) -> bytes:
        payload = kind + data
        return (
            struct.pack("!I", len(data))
            + payload
            + struct.pack("!I", zlib.crc32(payload))
        )

    pixel = b"\xff\x00\x00"
    channels = pixel + bytes([opacity]) if alpha else pixel
    rows = (b"\x00" + channels * width) * 2
    rows = rows[:1] + first_pixel + rows[4:]
    last_channels = last_pixel + bytes([opacity]) if alpha else last_pixel
    rows = rows[: -len(channels)] + last_channels
    return list(
        b"\x89PNG\r\n\x1a\n"
        + chunk(
            b"IHDR", struct.pack("!IIBBBBB", width, 2, 8, 6 if alpha else 2, 0, 0, 0)
        )
        + chunk(b"tEXt", b"Creation Time\x00" + metadata.encode("ascii"))
        + chunk(b"IDAT", zlib.compress(rows, compression))
        + chunk(b"IEND", b"")
    )


_VALIDATION_SETUP = r"""
// Use the actual GNOME PNG decoder; only Shell acquisition and timing are fake.
const GdkPixbuf = imports.gi.GdkPixbuf;
const timers = new Map();
GLib.timeout_add = (_priority, delay, callback) => {
    const id = nextId++;
    timers.set(id, {delay, callback});
    return id;
};
GLib.source_remove = id => timers.delete(id);
let area = {x: 12, y: 48, width: 3, height: 2};
window.get_frame_rect = () => ({...area});
let pendingScreenshot = null;
let deferScreenshot = false;
let screenshotSucceeded = true;
Shell.Screenshot.prototype.screenshot_window = function(frame, _cursor, _stream, cb) {
    screenshotIncludedFrame = frame;
    screenshotCount++;
    pendingScreenshot = () => cb(this, {});
    if (!deferScreenshot)
        pendingScreenshot();
};
Shell.Screenshot.prototype.screenshot_window_finish = () => [screenshotSucceeded, area];
imageBytes = new Uint8Array(fixtures.original);
const extension = new KyrinWindowCapturePrototype();
extension.enable();
const grant = request(extension, 'RequestSession', ':1.42');
dialogs.at(-1).buttons[1].action();
check(grant.reply.values[0] === true, 'grant failed');
const captured = request(extension, 'CaptureActiveWindow', ':1.42');
const captureId = JSON.parse(captured.reply.values[10]).capture_id;
function validate(id = captureId, regions = null) {
    const invocation = {
        get_sender: () => ':1.99',
        replies: [],
        return_value: reply => {invocation.replies.push(reply.values[0]);},
    };
    if (regions === null)
        extension.ValidateCaptureAsync([id], invocation);
    else
        extension.ValidateCaptureRegionsAsync([id, regions], invocation);
    return invocation;
}
function expectValidation(expected) {
    const invocation = validate();
    check(invocation.replies.length === 1 && invocation.replies[0] === expected,
        'unexpected validation result: ' + JSON.stringify(invocation.replies));
}
"""

_VALIDATION_CASES = {
    "identical": "expectValidation(true);",
    "metadata_same_length": """
        imageBytes = new Uint8Array(fixtures.metadataSameLength);
        expectValidation(true);
    """,
    "metadata_different_length": """
        imageBytes = new Uint8Array(fixtures.metadataDifferentLength);
        expectValidation(true);
    """,
    "compression": """
        imageBytes = new Uint8Array(fixtures.compression);
        expectValidation(true);
    """,
    "opaque_alpha": """
        imageBytes = new Uint8Array(fixtures.alpha);
        expectValidation(true);
    """,
    "pixel_changed": """
        imageBytes = new Uint8Array(fixtures.changed);
        expectValidation(false);
    """,
    "alpha_changed": """
        imageBytes = new Uint8Array(fixtures.transparent);
        expectValidation(false);
    """,
    "dimensions_changed": """
        imageBytes = new Uint8Array(fixtures.wider);
        expectValidation(false);
    """,
    "invalid_png": "imageBytes = new Uint8Array([1, 2, 3]); expectValidation(false);",
    "invalid_original": """
        extension._lastCapture.bytes = new Uint8Array([1, 2, 3]);
        expectValidation(false);
    """,
    "capture_id": """
        check(validate('wrong-id').replies[0] === false, 'wrong ID accepted');
    """,
    "expired": "monotonicUs += 11000000; expectValidation(false);",
    "capture_pending": "extension._capturePending = {}; expectValidation(false);",
    "disabled": "extension.disable(); expectValidation(false);",
    "token": "window.get_stable_sequence = () => 8; expectValidation(false);",
    "focus": "global.display.get_focus_window = () => null; expectValidation(false);",
    "geometry": "area.x++; expectValidation(false);",
    "screenshot_failed": "screenshotSucceeded = false; expectValidation(false);",
    "screenshot_error": """
        Shell.Screenshot.prototype.screenshot_window_finish = () => {
            throw new Error('screenshot failed');
        };
        expectValidation(false);
    """,
    "late_focus": """
        deferScreenshot = true;
        const invocation = validate();
        global.display.get_focus_window = () => null;
        pendingScreenshot();
        check(invocation.replies.join(',') === 'false', 'late focus change accepted');
    """,
    "late_token": """
        deferScreenshot = true;
        const invocation = validate();
        window.get_stable_sequence = () => 8;
        pendingScreenshot();
        check(invocation.replies.join(',') === 'false', 'late token change accepted');
    """,
    "snapshot_replaced": """
        deferScreenshot = true;
        const invocation = validate();
        extension._lastCapture = {...extension._lastCapture};
        pendingScreenshot();
        check(invocation.replies.join(',') === 'false', 'old snapshot accepted');
    """,
    "concurrent_validation": """
        deferScreenshot = true;
        const invocation = validate();
        expectValidation(false);
        pendingScreenshot();
        check(invocation.replies.join(',') === 'true', 'first validation lost');
    """,
    "timeout_then_late_callback": """
        deferScreenshot = true;
        const invocation = validate();
        const timeout = [...timers.values()].find(timer => timer.delay === 8000);
        check(timeout !== undefined, 'validation timeout missing');
        timeout.callback();
        pendingScreenshot();
        check(invocation.replies.length === 1 && invocation.replies[0] === false,
            'timeout was overwritten or callback replied twice');
        check(extension._validationPending === null, 'validation remained pending');
    """,
    "revoke_then_late_callback": """
        deferScreenshot = true;
        const invocation = validate();
        extension._revoke();
        pendingScreenshot();
        check(invocation.replies.length === 1 && invocation.replies[0] === false,
            'revocation was overwritten or callback replied twice');
    """,
    "duplicate_callback": """
        const invocation = validate();
        pendingScreenshot();
        check(invocation.replies.length === 1 && invocation.replies[0] === true,
            'callback replied twice');
    """,
}



_REGION_CASES = {
    "outside_animation": """
        imageBytes = new Uint8Array(fixtures.changed);
        check(validate(captureId, [[0, 0, 1, 1]]).replies[0] === true,
            'animation outside the evidence blocked the target');
    """,
    "target_moved": """
        extension._lastCapture.bytes = new Uint8Array(fixtures.targetChanged);
        imageBytes = new Uint8Array(fixtures.targetMoved);
        check(validate(captureId, [[0, 0, 1, 1]]).replies[0] === false,
            'target moved outside its original evidence accepted');
    """,
    "destroyed_window": """
        window.get_frame_rect = () => {throw new Error('window destroyed');};
        check(validate(captureId, [[0, 0, 1, 1]]).replies[0] === false,
            'destroyed window accepted');
    """,
    "target_changed": """
        imageBytes = new Uint8Array(fixtures.targetChanged);
        check(validate(captureId, [[0, 0, 1, 1]]).replies[0] === false,
            'changed or moved target accepted');
    """,
    "support_changed": """
        imageBytes = new Uint8Array(fixtures.changed);
        check(validate(captureId, [[0, 0, 1, 1], [2, 1, 1, 1]]).replies[0] === false,
            'changed supporting evidence accepted');
    """,
    "region_metadata": """
        imageBytes = new Uint8Array(fixtures.metadataDifferentLength);
        check(validate(captureId, [[0, 0, 1, 1]]).replies[0] === true,
            'metadata blocked stable evidence');
    """,
    "late_expiry": """
        deferScreenshot = true;
        const invocation = validate(captureId, [[0, 0, 1, 1]]);
        monotonicUs += 11000000;
        pendingScreenshot();
        check(invocation.replies.join(',') === 'false', 'expired evidence accepted');
    """,
    "future_evidence": """
        monotonicUs -= 1000000;
        check(validate(captureId, [[0, 0, 1, 1]]).replies[0] === false,
            'future evidence accepted');
    """,
    "late_frame": """
        deferScreenshot = true;
        const invocation = validate(captureId, [[0, 0, 1, 1]]);
        window.get_frame_rect = () => ({x: 11, y: 20, width: 800, height: 600});
        pendingScreenshot();
        check(invocation.replies.join(',') === 'false', 'moved frame accepted');
    """,
    "transient_focus": """
        deferScreenshot = true;
        const invocation = validate(captureId, [[0, 0, 1, 1]]);
        for (const callback of signals.values()) callback();
        pendingScreenshot();
        check(invocation.replies.join(',') === 'false', 'transient focus accepted');
    """,
}
for _name, _regions in {
    "empty": [], "negative": [[-1, 0, 1, 1]], "zero": [[0, 0, 0, 1]],
    "past_right": [[2, 0, 2, 1]], "past_bottom": [[0, 1, 1, 2]],
    "fractional": [[0.5, 0, 1, 1]], "bad_shape": [[0, 0, 1]],
}.items():
    _REGION_CASES["invalid_" + _name] = (
        "check(validate(captureId, " + json.dumps(_regions) + ").replies[0] === false, "
        "'invalid region accepted');"
    )
# Exercise the existing lifetime, focus, token and error guards through the new API.
for _name, _program in _VALIDATION_CASES.items():
    _REGION_CASES["guard_" + _name] = (
        "const wholeValidate = validate; "
        "validate = (id = captureId) => wholeValidate(id, [[0, 0, 3, 2]]);\n"
        + _program
    )


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


@pytest.mark.parametrize("case", {**_VALIDATION_CASES, **_REGION_CASES})
def test_gnome_capture_validation_compares_decoded_pixels(case: str) -> None:
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
    fixtures = {
        "original": _png(),
        "targetChanged": _png(first_pixel=b"\x00\x00\xff"),
        "targetMoved": _png(last_pixel=b"\x00\x00\xff"),
        "metadataSameLength": _png(metadata="later"),
        "metadataDifferentLength": _png(metadata="a different creation timestamp"),
        "compression": _png(compression=0),
        "alpha": _png(alpha=True),
        "transparent": _png(alpha=True, opacity=254),
        "changed": _png(last_pixel=b"\xfe\x00\x00"),
        "wider": _png(width=4),
    }
    program = (
        _FAKES
        + source
        + "\nconst fixtures = "
        + json.dumps(fixtures)
        + ";\n"
        + _VALIDATION_SETUP
        + {**_VALIDATION_CASES, **_REGION_CASES}[case]
        + "\nprint('GNOME capture validation: passed');"
    )
    result = subprocess.run(
        [gjs, "-c", program],
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )
    assert result.returncode == 0, result.stderr
    assert "capture validation: passed" in result.stdout


def test_region_signature_round_trips_on_an_isolated_dbus() -> None:
    """Verify busctl array encoding and GJS argument unpacking, without Shell."""
    gjs = shutil.which("gjs")
    dbus = shutil.which("dbus-run-session")
    busctl = shutil.which("busctl")
    if gjs is None or dbus is None or busctl is None:
        pytest.skip("GJS, busctl and dbus-run-session are required")
    xml_source = _EXTENSION.read_text().split("const INTERFACE_XML = `", 1)[1]
    xml = xml_source.split("`;", 1)[0]
    program = (
        "const xml = " + json.dumps(xml)
        + ";\nconst busctl = " + json.dumps(busctl) + ";"
        + r"""
const {Gio, GLib} = imports.gi;
const loop = new GLib.MainLoop(null, false);
let exported = null;
let passed = false;
let calls = 0;
const owner = Gio.bus_own_name(Gio.BusType.SESSION, 'org.kyrin.RegionTest',
    Gio.BusNameOwnerFlags.NONE,
    connection => {
        exported = Gio.DBusExportedObject.wrapJSObject(xml, {
            ValidateCaptureRegionsAsync([id, regions], invocation) {
                calls++;
                const expected = [[120, 80, 30, 10], [40, 20, 8, 8]];
                invocation.return_value(new GLib.Variant('(b)', [
                    id === 'capture-1' &&
                    JSON.stringify(regions) === JSON.stringify(expected),
                ]));
            },
        });
        exported.export(connection, '/org/kyrin/RegionTest');
    },
    () => {
        const client = Gio.Subprocess.new([
            busctl, '--user', '--json=short', 'call',
            'org.kyrin.RegionTest', '/org/kyrin/RegionTest',
            'org.kyrin.WindowCapturePrototype', 'ValidateCaptureRegions',
            'sa(iiii)', 'capture-1', '2',
            '120', '80', '30', '10', '40', '20', '8', '8',
        ], Gio.SubprocessFlags.STDOUT_PIPE | Gio.SubprocessFlags.STDERR_PIPE);
        client.communicate_utf8_async(null, null, (_source, result) => {
            const [, stdout, stderr] = client.communicate_utf8_finish(result);
            if (stderr) printerr(stderr);
            const response = JSON.parse(stdout);
            passed = client.get_successful() && response.type === 'b' &&
                response.data.length === 1 && response.data[0] === true && calls === 1;
            loop.quit();
        });
    },
    () => loop.quit());
GLib.timeout_add(GLib.PRIORITY_DEFAULT, 3000, () => {
    loop.quit();
    return GLib.SOURCE_REMOVE;
});
loop.run();
exported?.unexport();
Gio.bus_unown_name(owner);
if (!passed) throw new Error('region D-Bus round trip failed');
print('region D-Bus round trip: passed');
"""
    )
    result = subprocess.run(
        [dbus, "--", gjs, "-c", program],
        capture_output=True, text=True, timeout=10, check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "region D-Bus round trip: passed" in result.stdout
