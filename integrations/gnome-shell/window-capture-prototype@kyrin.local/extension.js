import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import Shell from 'gi://Shell';
import St from 'gi://St';

import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';
import * as ModalDialog from 'resource:///org/gnome/shell/ui/modalDialog.js';

const INTERFACE_XML = `<node>
  <interface name="org.kyrin.WindowCapturePrototype">
    <method name="RequestSession">
      <arg name="granted" type="b" direction="out"/>
    </method>
    <method name="RequestPersistentSession">
      <arg name="token" type="s" direction="in"/>
      <arg name="granted" type="b" direction="out"/>
    </method>
    <method name="RevokeSession">
      <arg name="revoked" type="b" direction="out"/>
    </method>
    <method name="CaptureActiveWindow">
      <arg name="app_id" type="s" direction="out"/>
      <arg name="pid" type="u" direction="out"/>
      <arg name="capture_x" type="i" direction="out"/>
      <arg name="capture_y" type="i" direction="out"/>
      <arg name="capture_width" type="i" direction="out"/>
      <arg name="capture_height" type="i" direction="out"/>
      <arg name="frame_x" type="i" direction="out"/>
      <arg name="frame_y" type="i" direction="out"/>
      <arg name="frame_width" type="i" direction="out"/>
      <arg name="frame_height" type="i" direction="out"/>
      <arg name="geometry" type="s" direction="out"/>
      <arg name="png" type="ay" direction="out"/>
    </method>
    <method name="ValidateCapture">
      <arg name="capture_id" type="s" direction="in"/>
      <arg name="current" type="b" direction="out"/>
    </method>
  </interface>
</node>`;

const MAX_IMAGE_BYTES = 16 * 1024 * 1024;
const CAPTURE_TIMEOUT_MS = 8000;
const CONSENT_TIMEOUT_MS = 20000;
const KYRIN_SERVICE = 'org.kyrin.Desktop';
const GRANT_FILE = GLib.build_filenamev([
    GLib.get_user_data_dir(), 'kyrin', 'permissions', 'screen-grant.sha256',
]);

function tokenHash(token) {
    if (typeof token !== 'string' || !/^[0-9a-f]{64}$/.test(token))
        return null;
    return GLib.compute_checksum_for_string(GLib.ChecksumType.SHA256, token, -1);
}

function rememberedHash() {
    try {
        const [ok, contents] = GLib.file_get_contents(GRANT_FILE);
        return ok ? new TextDecoder().decode(contents).trim() : null;
    } catch (_error) {
        return null;
    }
}

function rememberHash(hash) {
    try {
        if (GLib.mkdir_with_parents(GLib.path_get_dirname(GRANT_FILE), 0o700) !== 0)
            return false;
        if (!GLib.file_set_contents(GRANT_FILE, hash))
            return false;
        return GLib.chmod(GRANT_FILE, 0o600) === 0;
    } catch (_error) {
        return false;
    }
}

function unavailableCapture(invocation) {
    invocation.return_value(new GLib.Variant(
        '(suiiiiiiiisay)', ['', 0, 0, 0, 0, 0, 0, 0, 0, 0, '', new Uint8Array()]));
}

export default class KyrinWindowCapturePrototype extends Extension {
    enable() {
        this._enabled = true;
        this._capturePending = null;
        this._validationPending = null;
        this._lastCapture = null;
        this._consentPending = null;
        this._pendingSender = null;
        this._sessionSender = null;
        this._ownerSignalId = Gio.DBus.session.signal_subscribe(
            'org.freedesktop.DBus', 'org.freedesktop.DBus', 'NameOwnerChanged',
            '/org/freedesktop/DBus', KYRIN_SERVICE, Gio.DBusSignalFlags.NONE,
            (_connection, _sender, _path, _interface, _signal, parameters) => {
                const [_name, oldOwner, newOwner] = parameters.deepUnpack();
                if (oldOwner === this._sessionSender && newOwner !== oldOwner)
                    this._revoke();
                if (oldOwner === this._pendingSender && newOwner !== oldOwner)
                    this._consentPending?.deny();
            });
        this._dbusObject = Gio.DBusExportedObject.wrapJSObject(INTERFACE_XML, this);
        this._dbusObject.export(Gio.DBus.session, '/org/kyrin/WindowCapturePrototype');
    }

    disable() {
        this._enabled = false;
        this._consentPending?.deny();
        this._pendingSender = null;
        this._revoke();
        Gio.DBus.session.signal_unsubscribe(this._ownerSignalId);
        this._dbusObject?.unexport();
        this._dbusObject = null;
    }

    _revoke() {
        this._sessionSender = null;
        this._lastCapture = null;
        this._validationPending?.finish(false);
        this._capturePending?.finish(null);
    }

    _verifyOwner(sender, callback) {
        Gio.DBus.session.call(
            'org.freedesktop.DBus', '/org/freedesktop/DBus',
            'org.freedesktop.DBus', 'GetNameOwner',
            new GLib.Variant('(s)', [KYRIN_SERVICE]),
            new GLib.VariantType('(s)'), Gio.DBusCallFlags.NONE, 2000, null,
            (connection, result) => {
                let matches = false;
                try {
                    const [owner] = connection.call_finish(result).deepUnpack();
                    matches = owner === sender;
                } catch (_error) {
                    // No owner or bus failure: deny.
                }
                callback(this._enabled && matches);
            });
    }

    RequestSessionAsync(_params, invocation) {
        this._requestSession(invocation, null);
    }

    RequestPersistentSessionAsync(params, invocation) {
        const hash = tokenHash(params[0]);
        if (hash === null) {
            invocation.return_value(new GLib.Variant('(b)', [false]));
            return;
        }
        this._requestSession(invocation, hash);
    }

    _requestSession(invocation, persistentHash) {
        if (this._capturePending !== null || this._consentPending !== null) {
            invocation.return_value(new GLib.Variant('(b)', [false]));
            return;
        }
        const sender = invocation.get_sender();
        if (!sender || !sender.startsWith(':')) {
            invocation.return_value(new GLib.Variant('(b)', [false]));
            return;
        }
        if (sender === this._sessionSender) {
            invocation.return_value(new GLib.Variant('(b)', [true]));
            return;
        }
        if (this._sessionSender !== null) {
            invocation.return_value(new GLib.Variant('(b)', [false]));
            return;
        }
        const pending = {deny: () => {
            if (this._consentPending !== pending)
                return;
            this._consentPending = null;
            this._pendingSender = null;
            invocation.return_value(new GLib.Variant('(b)', [false]));
        }};
        this._consentPending = pending;
        this._pendingSender = sender;
        this._verifyOwner(sender, verified => {
            if (this._consentPending !== pending)
                return;
            if (!verified) {
                this._consentPending = null;
                this._pendingSender = null;
                invocation.return_value(new GLib.Variant('(b)', [false]));
                return;
            }
            if (persistentHash !== null && rememberedHash() === persistentHash) {
                this._consentPending = null;
                this._pendingSender = null;
                this._sessionSender = sender;
                invocation.return_value(new GLib.Variant('(b)', [true]));
                return;
            }
            this._askSessionConsent(sender, invocation, persistentHash);
        });
    }

    _askSessionConsent(sender, invocation, persistentHash = null) {
        const dialog = new ModalDialog.ModalDialog({destroyOnClose: true});
        dialog.contentLayout.add_child(new St.Label({
            text: 'Allow KYRIN to read the active window until you turn it off?\n' +
                'The current owner of KYRIN\'s session name can request images.\n' +
                'No image is saved. Turn this off in KYRIN at any time.',
            style_class: 'kyrin-capture-consent-label',
        }));
        let decided = false;
        let finished = false;
        let consentTimedOut = false;
        const finish = granted => {
            if (finished)
                return;
            finished = true;
            this._consentPending = null;
            this._pendingSender = null;
            if (granted && persistentHash !== null)
                granted = rememberHash(persistentHash);
            if (granted)
                this._sessionSender = sender;
            invocation.return_value(new GLib.Variant('(b)', [granted]));
        };
        const decide = allowed => {
            if (decided)
                return;
            decided = true;
            if (!consentTimedOut)
                GLib.source_remove(consentTimeoutId);
            dialog.close();
            if (!allowed || !this._enabled) {
                finish(false);
                return;
            }
            // Check again: the name may have changed owner during the prompt.
            this._verifyOwner(sender, verified => finish(verified));
        };
        dialog.setButtons([
            {label: 'Deny', action: () => decide(false)},
            {label: persistentHash === null ? 'Allow for this session' : 'Remember permission',
                action: () => decide(true)},
        ]);
        const consentTimeoutId = GLib.timeout_add(
            GLib.PRIORITY_DEFAULT, CONSENT_TIMEOUT_MS, () => {
                consentTimedOut = true;
                decide(false);
                return GLib.SOURCE_REMOVE;
            });
        this._consentPending = {deny: () => {
            if (decided)
                finish(false);
            else
                decide(false);
        }};
        dialog.connect('closed', () => decide(false));
        try {
            if (!dialog.open())
                decide(false);
        } catch (_error) {
            decide(false);
        }
    }

    RevokeSessionAsync(_params, invocation) {
        const sender = invocation.get_sender();
        const authorized = sender !== null &&
            (sender === this._sessionSender || sender === this._pendingSender);
        if (sender === this._pendingSender)
            this._consentPending?.deny();
        if (sender === this._sessionSender)
            this._revoke();
        let removed = true;
        if (authorized) {
            try {
                if (GLib.unlink(GRANT_FILE) !== 0 &&
                    GLib.file_test(GRANT_FILE, GLib.FileTest.EXISTS))
                    removed = false;
            } catch (error) {
                if (!GLib.file_test(GRANT_FILE, GLib.FileTest.EXISTS))
                    removed = true;
                else
                    removed = false;
            }
        }
        invocation.return_value(new GLib.Variant('(b)', [authorized && removed]));
    }

    CaptureActiveWindowAsync(_params, invocation) {
        const sender = invocation.get_sender();
        if (!sender || sender !== this._sessionSender ||
            this._capturePending !== null) {
            unavailableCapture(invocation);
            return;
        }
        const window = global.display.get_focus_window();
        const app = window === null
            ? null
            : Shell.WindowTracker.get_default().get_window_app(window);
        // GNOME gives unregistered windows temporary "window:N" Shell.App IDs.
        // Such an ID cannot identify an installed application for a later action.
        const appId = app !== null && !app.is_window_backed()
            ? app.get_id()
            : '';
        const pid = window?.get_pid() ?? 0;
        if (!appId || pid <= 0) {
            unavailableCapture(invocation);
            return;
        }

        this._capture(window, appId, pid, invocation);
    }

    _capture(window, appId, pid, invocation) {
        this._lastCapture = null;
        const frame = window.get_frame_rect();
        const monitorId = window.get_monitor();
        const monitorScale = global.display.get_monitor_scale(monitorId);
        const windowToken = String(window.get_stable_sequence());
        let focusChanged = false;
        let completed = false;
        let timedOut = false;
        const focusSignal = global.display.connect('notify::focus-window', () => {
            focusChanged = true;
        });
        const finish = (bytes, area = null) => {
            if (completed)
                return;
            completed = true;
            global.display.disconnect(focusSignal);
            if (!timedOut)
                GLib.source_remove(timeoutId);
            this._capturePending = null;
            let frameUnchanged = false;
            try {
                const currentFrame = window.get_frame_rect();
                frameUnchanged = currentFrame.x === frame.x &&
                    currentFrame.y === frame.y &&
                    currentFrame.width === frame.width &&
                    currentFrame.height === frame.height;
            } catch (_error) {
                // A destroyed window cannot remain an action target.
            }
            if (bytes === null || !area || focusChanged || !frameUnchanged ||
                invocation.get_sender() !== this._sessionSender ||
                global.display.get_focus_window() !== window ||
                ![area.x, area.y, area.width, area.height].every(Number.isInteger) ||
                area.width <= 0 || area.height <= 0 ||
                bytes.length === 0 || bytes.length > MAX_IMAGE_BYTES) {
                unavailableCapture(invocation);
                return;
            }
            // The PNG may include a window shadow. The monitor scale is read
            // independently, so the remaining pixels are explicit padding.
            const pngWidth = (bytes[16] * 0x1000000) +
                (bytes[17] << 16) + (bytes[18] << 8) + bytes[19];
            const pngHeight = (bytes[20] * 0x1000000) +
                (bytes[21] << 16) + (bytes[22] << 8) + bytes[23];
            const extraWidth = pngWidth - Math.round(area.width * monitorScale);
            const extraHeight = pngHeight - Math.round(area.height * monitorScale);
            if (bytes.length < 24 || !Number.isFinite(monitorScale) ||
                monitorScale <= 0 || monitorId < 0 ||
                extraWidth < 0 || extraHeight < 0 ||
                extraWidth > 256 || extraHeight > 256) {
                unavailableCapture(invocation);
                return;
            }
            const captureId = GLib.uuid_string_random();
            const capturedAt = GLib.get_monotonic_time() / 1000000;
            const geometry = JSON.stringify({
                monitor_id: monitorId,
                scale_x: monitorScale,
                scale_y: monitorScale,
                padding: [Math.floor(extraWidth / 2), Math.floor(extraHeight / 2),
                    Math.ceil(extraWidth / 2), Math.ceil(extraHeight / 2)],
                window_token: windowToken,
                capture_id: captureId,
                captured_at: capturedAt,
            });
            this._lastCapture = {
                id: captureId, at: capturedAt, window, token: windowToken,
                area: [area.x, area.y, area.width, area.height], bytes,
            };
            GLib.timeout_add(GLib.PRIORITY_DEFAULT, 10000, () => {
                if (this._lastCapture?.id === captureId)
                    this._lastCapture = null;
                return GLib.SOURCE_REMOVE;
            });
            invocation.return_value(new GLib.Variant('(suiiiiiiiisay)', [
                appId, pid, area.x, area.y, area.width, area.height,
                frame.x, frame.y, frame.width, frame.height, geometry, bytes,
            ]));
        };
        const timeoutId = GLib.timeout_add(
            GLib.PRIORITY_DEFAULT, CAPTURE_TIMEOUT_MS, () => {
                timedOut = true;
                finish(null);
                return GLib.SOURCE_REMOVE;
            });
        this._capturePending = {finish};

        const image = Gio.MemoryOutputStream.new_resizable();
        const screenshot = new Shell.Screenshot();
        try {
            // Click coordinates use Meta.Window.get_frame_rect(); capture the
            // same frame so OCR coordinates share that origin and size.
            screenshot.screenshot_window(true, false, image, (_source, result) => {
                try {
                    const outcome = screenshot.screenshot_window_finish(result);
                    const succeeded = Array.isArray(outcome) && outcome[0];
                    const area = Array.isArray(outcome) ? outcome[1] : null;
                    if (!succeeded || !area) {
                        finish(null);
                        return;
                    }
                    image.close(null);
                    finish(image.steal_as_bytes().get_data(), area);
                } catch (_error) {
                    finish(null);
                }
            });
        } catch (_error) {
            finish(null);
        }
    }

    ValidateCaptureAsync([captureId], invocation) {
        const snapshot = this._lastCapture;
        const window = global.display.get_focus_window();
        const valid = this._enabled && snapshot !== null &&
            captureId === snapshot.id &&
            GLib.get_monotonic_time() / 1000000 - snapshot.at <= 10 &&
            window === snapshot.window &&
            String(window.get_stable_sequence()) === snapshot.token &&
            this._capturePending === null && this._validationPending === null;
        if (!valid) {
            invocation.return_value(new GLib.Variant('(b)', [false]));
            return;
        }
        let completed = false;
        let timedOut = false;
        const finish = current => {
            if (completed)
                return;
            completed = true;
            if (!timedOut)
                GLib.source_remove(timeoutId);
            this._validationPending = null;
            invocation.return_value(new GLib.Variant('(b)', [current]));
        };
        const timeoutId = GLib.timeout_add(
            GLib.PRIORITY_DEFAULT, CAPTURE_TIMEOUT_MS, () => {
                timedOut = true;
                finish(false);
                return GLib.SOURCE_REMOVE;
            });
        this._validationPending = {finish};
        const image = Gio.MemoryOutputStream.new_resizable();
        const screenshot = new Shell.Screenshot();
        try {
            screenshot.screenshot_window(true, false, image, (_source, result) => {
                try {
                    const [succeeded, area] = screenshot.screenshot_window_finish(result);
                    image.close(null);
                    const bytes = image.steal_as_bytes().get_data();
                    const original = snapshot.bytes;
                    let same = succeeded && area && bytes.length === original.length &&
                        [area.x, area.y, area.width, area.height].every(
                            (value, index) => value === snapshot.area[index]);
                    if (same) {
                        for (let index = 0; index < bytes.length; index++) {
                            if (bytes[index] !== original[index]) {
                                same = false;
                                break;
                            }
                        }
                    }
                    finish(Boolean(same && this._lastCapture === snapshot &&
                        global.display.get_focus_window() === window &&
                        String(window.get_stable_sequence()) === snapshot.token));
                } catch (_error) {
                    finish(false);
                }
            });
        } catch (_error) {
            finish(false);
        }
    }
}
