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
    <method name="RevokeSession">
      <arg name="revoked" type="b" direction="out"/>
    </method>
    <method name="CaptureActiveWindow">
      <arg name="app_id" type="s" direction="out"/>
      <arg name="pid" type="u" direction="out"/>
      <arg name="png" type="ay" direction="out"/>
    </method>
  </interface>
</node>`;

const MAX_IMAGE_BYTES = 16 * 1024 * 1024;
const CAPTURE_TIMEOUT_MS = 8000;
const CONSENT_TIMEOUT_MS = 20000;
const KYRIN_SERVICE = 'org.kyrin.Desktop';

function unavailableCapture(invocation) {
    invocation.return_value(new GLib.Variant('(suay)', ['', 0, new Uint8Array()]));
}

export default class KyrinWindowCapturePrototype extends Extension {
    enable() {
        this._enabled = true;
        this._capturePending = null;
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
            this._askSessionConsent(sender, invocation);
        });
    }

    _askSessionConsent(sender, invocation) {
        const dialog = new ModalDialog.ModalDialog({destroyOnClose: true});
        dialog.contentLayout.add_child(new St.Label({
            text: 'Allow KYRIN to read the active window during this app session?\n' +
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
            {label: 'Allow for this session', action: () => decide(true)},
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
        invocation.return_value(new GLib.Variant('(b)', [authorized]));
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
        let focusChanged = false;
        let completed = false;
        let timedOut = false;
        const focusSignal = global.display.connect('notify::focus-window', () => {
            focusChanged = true;
        });
        const finish = bytes => {
            if (completed)
                return;
            completed = true;
            global.display.disconnect(focusSignal);
            if (!timedOut)
                GLib.source_remove(timeoutId);
            this._capturePending = null;
            if (bytes === null || focusChanged ||
                invocation.get_sender() !== this._sessionSender ||
                global.display.get_focus_window() !== window ||
                bytes.length === 0 || bytes.length > MAX_IMAGE_BYTES) {
                unavailableCapture(invocation);
                return;
            }
            invocation.return_value(new GLib.Variant('(suay)', [appId, pid, bytes]));
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
            screenshot.screenshot_window(false, false, image, (_source, result) => {
                try {
                    const outcome = screenshot.screenshot_window_finish(result);
                    const succeeded = Array.isArray(outcome) ? outcome[0] : outcome;
                    if (!succeeded) {
                        finish(null);
                        return;
                    }
                    image.close(null);
                    finish(image.steal_as_bytes().get_data());
                } catch (_error) {
                    finish(null);
                }
            });
        } catch (_error) {
            finish(null);
        }
    }
}
