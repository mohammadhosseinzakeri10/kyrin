import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import Shell from 'gi://Shell';

import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import {WindowPicker} from './windowPicker.js';
import {WindowCloseConfirmation} from './closeConfirmation.js';

const INTERFACE_XML = `<node>
  <interface name="org.kyrin.ActiveApp">
    <method name="GetCapabilities">
      <arg name="manifest" type="s" direction="out"/>
    </method>
    <method name="GetActiveApp">
      <arg name="app_id" type="s" direction="out"/>
    </method>
    <method name="GetActiveWindow">
      <arg name="app_id" type="s" direction="out"/>
      <arg name="pid" type="u" direction="out"/>
    </method>
    <method name="GetActiveWindowToken">
      <arg name="window_token" type="s" direction="out"/>
    </method>
    <method name="GetActiveWindowAndPointer">
      <arg name="app_id" type="s" direction="out"/>
      <arg name="pid" type="u" direction="out"/>
      <arg name="x" type="i" direction="out"/>
      <arg name="y" type="i" direction="out"/>
      <arg name="width" type="i" direction="out"/>
      <arg name="height" type="i" direction="out"/>
      <arg name="pointer_x" type="i" direction="out"/>
      <arg name="pointer_y" type="i" direction="out"/>
    </method>
    <method name="HasAppWindow">
      <arg name="appId" type="s" direction="in"/>
      <arg name="presence" type="s" direction="out"/>
    </method>
    <method name="CountAppWindows">
      <arg name="appId" type="s" direction="in"/>
      <arg name="count" type="i" direction="out"/>
    </method>
    <method name="ShowAllWindows">
      <arg name="status" type="s" direction="out"/>
    </method>
    <method name="ShowOpenWindows">
      <arg name="allowed_app_ids" type="as" direction="in"/>
      <arg name="status" type="s" direction="out"/>
    </method>
    <method name="ActivateShownOpenWindow">
      <arg name="number" type="u" direction="in"/>
      <arg name="status" type="s" direction="out"/>
    </method>
    <method name="CloseShownOpenWindow">
      <arg name="number" type="u" direction="in"/>
      <arg name="allowed_close_ids" type="as" direction="in"/>
      <arg name="status" type="s" direction="out"/>
    </method>
    <method name="ActivateShownOpenApp">
      <arg name="app_id" type="s" direction="in"/>
      <arg name="status" type="s" direction="out"/>
    </method>
    <method name="HideOpenWindows">
      <arg name="status" type="s" direction="out"/>
    </method>
    <method name="ShowAppWindows">
      <arg name="app_id" type="s" direction="in"/>
      <arg name="status" type="s" direction="out"/>
    </method>
    <method name="ActivateShownAppWindow">
      <arg name="app_id" type="s" direction="in"/>
      <arg name="number" type="u" direction="in"/>
      <arg name="status" type="s" direction="out"/>
    </method>
    <method name="CloseShownAppWindow">
      <arg name="app_id" type="s" direction="in"/>
      <arg name="number" type="u" direction="in"/>
      <arg name="status" type="s" direction="out"/>
    </method>
    <method name="HideAppWindows">
      <arg name="app_id" type="s" direction="in"/>
      <arg name="status" type="s" direction="out"/>
    </method>
    <method name="ActivateExistingApp">
      <arg name="app_id" type="s" direction="in"/>
      <arg name="status" type="s" direction="out"/>
    </method>
    <method name="PrepareWindowClose">
      <arg name="app_id" type="s" direction="in"/>
      <arg name="number" type="u" direction="in"/>
      <arg name="observation" type="s" direction="out"/>
    </method>
    <method name="CloseAuthorizedWindow">
      <arg type="s" direction="in" name="generation"/>
      <arg type="s" direction="out" name="result"/>
    </method>
    <method name="ConfirmWindowClose">
      <arg name="generation" type="s" direction="in"/>
      <arg name="language" type="s" direction="in"/>
      <arg name="decision" type="s" direction="out"/>
    </method>
    <method name="CloseConfirmedWindow">
      <arg name="generation" type="s" direction="in"/>
      <arg name="status" type="s" direction="out"/>
    </method>
    <method name="ControlAppWindow">
      <arg name="app_id" type="s" direction="in"/>
      <arg name="operation" type="s" direction="in"/>
      <arg name="status" type="s" direction="out"/>
      <arg name="window_token" type="s" direction="out"/>
    </method>
    <method name="GetAppWindowState">
      <arg name="app_id" type="s" direction="in"/>
      <arg name="window_token" type="s" direction="in"/>
      <arg name="state" type="s" direction="out"/>
    </method>
  </interface>
</node>`;

export default class KyrinActiveAppExtension extends Extension {
    // This literal belongs to the loaded module; metadata on disk may be newer.
    GetCapabilities() {
        return JSON.stringify({"protocol_version": 1, "build_id": "active-app@kyrin.local-2026-10-25-persistent-permissions", "capabilities": ["GetActiveApp", "GetActiveWindow", "GetActiveWindowToken", "GetActiveWindowAndPointer", "HasAppWindow", "CountAppWindows", "ShowAllWindows", "ShowOpenWindows", "ActivateShownOpenWindow", "CloseShownOpenWindow", "ActivateShownOpenApp", "HideOpenWindows", "ShowAppWindows", "ActivateShownAppWindow", "CloseShownAppWindow", "HideAppWindows", "ActivateExistingApp", "PrepareWindowClose", "ConfirmWindowClose", "CloseConfirmedWindow", "CloseAuthorizedWindow", "ControlAppWindow", "GetAppWindowState"]});
    }

    enable() {
        this._pendingClose = null;
        this._closeDialog = null;
        this._picker = null;
        this._shownWindows = null;
        this._shownOpen = null;
        this._closeFocusSignal = global.display.connect('notify::focus-window', () => {
            this._pendingClose = null;
            this._closeDialog?.cancel();
        });
        this._dbusObject = Gio.DBusExportedObject.wrapJSObject(INTERFACE_XML, this);
        this._dbusObject.export(Gio.DBus.session, '/org/kyrin/ActiveApp');
    }

    disable() {
        global.display.disconnect(this._closeFocusSignal);
        this._closeFocusSignal = null;
        this._clearPicker();
        this._dbusObject?.unexport();
        this._dbusObject = null;
    }

    GetActiveApp() {
        const window = global.display.get_focus_window();
        if (window === null)
            return '';

        const app = Shell.WindowTracker.get_default().get_window_app(window);
        return app?.get_id() ?? '';
    }

    GetActiveWindow() {
        const window = global.display.get_focus_window();
        if (window === null)
            return ['', 0];

        const app = Shell.WindowTracker.get_default().get_window_app(window);
        const pid = window.get_pid();
        return [app?.get_id() ?? '', pid > 0 ? pid : 0];
    }

    GetActiveWindowToken() {
        const window = global.display.get_focus_window();
        return window === null ? '' : String(window.get_stable_sequence());
    }

    GetActiveWindowAndPointer() {
        const window = global.display.get_focus_window();
        if (window === null)
            return ['', 0, 0, 0, 0, 0, 0, 0];
        const app = Shell.WindowTracker.get_default().get_window_app(window);
        const pid = window.get_pid();
        const rect = window.get_frame_rect();
        const [pointerX, pointerY] = global.get_pointer();
        return [
            app?.get_id() ?? '', pid > 0 ? pid : 0,
            rect.x, rect.y, rect.width, rect.height,
            Math.round(pointerX), Math.round(pointerY),
        ];
    }

    HasAppWindow(appId) {
        const windows = this._appWindows(appId);
        if (windows === null)
            return 'unknown';
        return windows.length > 0 ? 'open' : 'closed';
    }

    CountAppWindows(appId) {
        const windows = this._appWindows(appId);
        return windows === null ? -1 : windows.length;
    }

    ShowAllWindows() {
        Main.overview.show();
        return 'requested';
    }

    _clearPicker() {
        this._pendingClose = null;
        this._closeDialog?.cancel();
        this._picker?.destroy();
        this._picker = null;
        this._shownWindows = null;
        this._shownOpen = null;
    }

    ShowOpenWindows(allowedIds) {
        this._clearPicker();
        if (!Array.isArray(allowedIds) || allowedIds.length === 0)
            return 'unknown';
        const apps = [];
        for (const id of new Set(allowedIds)) {
            if (!id.endsWith('.desktop') || id.includes('/') || id.includes('\\'))
                return 'unknown';
            const app = Shell.AppSystem.get_default().lookup_app(id);
            if (app)
                apps.push({id, app});
        }
        const choices = apps.flatMap(({id, app}) => app.get_windows().map(window => ({
            appId: id,
            name: app.get_name(),
            token: String(window.get_stable_sequence()),
            window,
        }))).sort((a, b) => a.name.localeCompare(b.name) ||
            Number(a.token) - Number(b.token)).slice(0, 99);
        if (choices.length === 0)
            return 'no_window';
        this._shownOpen = choices.map(({appId, token}) => ({appId, token}));
        this._picker = new WindowPicker(
            number => this.ActivateShownOpenWindow(number),
            () => this._clearPicker()
        );
        if (!this._picker.show(choices.map(choice => choice.window),
            choices.map(choice => choice.name), 'Open windows — say a number or app name')) {
            this._clearPicker();
            return 'unavailable';
        }
        return 'requested';
    }

    ActivateShownOpenWindow(number) {
        if (this._shownOpen === null)
            return 'not_shown';
        if (!Number.isInteger(number) || number < 1 || number > this._shownOpen.length)
            return 'stale';
        const {appId, token} = this._shownOpen[number - 1];
        const window = this._appWindows(appId)?.find(
            item => String(item.get_stable_sequence()) === token);
        if (!window) {
            this._clearPicker();
            return 'stale';
        }
        this._clearPicker();
        Main.activateWindow(window, global.display.get_current_time_roundtrip());
        return 'requested';
    }

    CloseShownOpenWindow(_number, _allowedCloseIds) {
        return 'confirmation_required';
    }

    ActivateShownOpenApp(appId) {
        if (this._shownOpen === null || !appId.endsWith('.desktop'))
            return 'not_shown';
        const choices = this._shownOpen.flatMap((item, index) =>
            item.appId === appId ? [index + 1] : []);
        if (choices.length === 0)
            return 'not_shown';
        return choices.length === 1
            ? this.ActivateShownOpenWindow(choices[0]) : 'ambiguous';
    }

    HideOpenWindows() {
        this._clearPicker();
        return 'requested';
    }

    ShowAppWindows(appId) {
        this._clearPicker();
        // V1 has one reviewed terminal binding; do not expose other apps in
        // this new preview surface merely because a local D-Bus caller asks.
        if (appId !== 'org.gnome.Ptyxis.desktop')
            return 'unknown';
        const windows = this._appWindows(appId);
        if (windows === null || windows.length < 2)
            return 'no_window';
        this._shownWindows = windows.map(window => String(window.get_stable_sequence()));
        this._picker = new WindowPicker(
            number => this.ActivateShownAppWindow(appId, number),
            () => this._clearPicker()
        );
        if (!this._picker.show(windows)) {
            this._clearPicker();
            return 'unavailable';
        }
        return 'requested';
    }

    ActivateShownAppWindow(appId, number) {
        if (appId !== 'org.gnome.Ptyxis.desktop' || this._shownWindows === null)
            return 'not_shown';
        if (!Number.isInteger(number) || number < 1 || number > this._shownWindows.length)
            return 'stale';
        const token = this._shownWindows[number - 1];
        const windows = this._appWindows(appId);
        const window = windows?.find(item => String(item.get_stable_sequence()) === token);
        if (window === undefined || window === null) {
            this._clearPicker();
            return 'stale';
        }
        this._clearPicker();
        Main.activateWindow(window, global.display.get_current_time_roundtrip());
        return 'requested';
    }

    CloseShownAppWindow(_appId, _number) {
        return 'confirmation_required';
    }

    HideAppWindows(appId) {
        if (appId !== 'org.gnome.Ptyxis.desktop')
            return 'unknown';
        this._clearPicker();
        return 'requested';
    }

    ActivateExistingApp(appId) {
        if (!appId.endsWith('.desktop') || appId.includes('/') || appId.includes('\\'))
            return 'unknown';

        const app = Shell.AppSystem.get_default().lookup_app(appId);
        if (app === null || app.get_n_windows() === 0)
            return 'no_window';

        // Shell.App.activate_window() may mark a voice-triggered request as
        // "ready" when its event timestamp is older than the last input.
        // Use the same window path as GNOME's dock for this allowed action.
        const windows = app.get_windows();
        const focused = global.display.get_focus_window();
        const window = windows.length === 1
            ? windows[0]
            : windows.includes(focused) &&
              Shell.WindowTracker.get_default().get_window_app(focused)?.get_id() === appId
                ? focused : null;
        if (window === null)
            return 'multiple_windows';
        Main.activateWindow(window, global.display.get_current_time_roundtrip());
        return 'requested';
    }

    _appWindows(appId) {
        if (!appId.endsWith('.desktop') || appId.includes('/') || appId.includes('\\'))
            return null;
        const app = Shell.AppSystem.get_default().lookup_app(appId);
        return app?.get_windows() ?? [];
    }

    GetAppWindowState(appId, token) {
        const windows = this._appWindows(appId);
        if (windows === null || !/^[0-9]+$/.test(token))
            return 'unknown';
        const window = windows.find(item => String(item.get_stable_sequence()) === token);
        if (window === undefined)
            return 'no_window';
        return JSON.stringify({
            minimized: window.minimized,
            focused: global.display.get_focus_window() === window,
            maximized: window.is_maximized(),
            fullscreen: window.is_fullscreen(),
        });
    }

    _closeCandidate(appId, number) {
        if (number > 0) {
            const choice = appId === ''
                ? this._shownOpen?.[number - 1]
                : appId === 'org.gnome.Ptyxis.desktop' && this._shownWindows
                    ? {appId, token: this._shownWindows[number - 1]} : null;
            if (!choice?.token)
                return null;
            const window = this._appWindows(choice.appId)?.find(
                item => String(item.get_stable_sequence()) === choice.token);
            return window ? {appId: choice.appId, window} : null;
        }
        const windows = this._appWindows(appId);
        if (!windows?.length)
            return null;
        const focus = global.display.get_focus_window();
        const window = windows.length === 1 ? windows[0]
            : windows.includes(focus) ? focus : null;
        return window ? {appId, window} : null;
    }

    PrepareWindowClose(appId, number) {
        this._closeDialog?.cancel();
        this._pendingClose = null;
        if (!Number.isInteger(number) || number < 0 || number > 99)
            return '';
        const candidate = this._closeCandidate(appId, number);
        if (!candidate || !candidate.window.can_close() || candidate.window.get_pid() <= 0)
            return '';
        // Release the picker before showing the per-window confirmation.
        // Retain only the numbered identity snapshot, never picker input.
        this._picker?.destroy();
        this._picker = null;
        const observed = GLib.get_monotonic_time() / 1000000;
        const observation = {
            app_id: candidate.appId,
            process_id: candidate.window.get_pid(),
            window_token: String(candidate.window.get_stable_sequence()),
            generation: GLib.uuid_string_random(),
            observed_at: observed,
            deadline: observed + 10,
        };
        this._pendingClose = {
            observation, appId, number, window: candidate.window,
            focus: global.display.get_focus_window(),
            snapshot: appId === '' ? this._shownOpen : this._shownWindows,
        };
        return JSON.stringify(observation);
    }

    ConfirmWindowCloseAsync([generation, language], invocation) {
        const pending = this._pendingClose;
        const reply = value => invocation.return_value(new GLib.Variant('(s)', [value]));
        if (!pending || pending.approved || this._closeDialog ||
            pending.observation.generation !== generation ||
            GLib.get_monotonic_time() / 1000000 >= pending.observation.deadline ||
            global.display.get_focus_window() !== pending.focus) {
            reply('declined');
            return;
        }
        let watch = null;
        const dialog = new WindowCloseConfirmation(approved => {
            if (watch !== null)
                Gio.bus_unwatch_name(watch);
            if (this._closeDialog === dialog)
                this._closeDialog = null;
            const accepted = approved && this._pendingClose === pending &&
                GLib.get_monotonic_time() / 1000000 < pending.observation.deadline &&
                global.display.get_focus_window() === pending.focus;
            pending.approved = accepted;
            if (!accepted && this._pendingClose === pending)
                this._pendingClose = null;
            reply(accepted ? 'approved' : 'declined');
        });
        this._closeDialog = dialog;
        // Cancellation/timeout kills the busctl caller; dismiss its dialog too.
        watch = Gio.bus_watch_name_on_connection(invocation.get_connection(),
            invocation.get_sender(), Gio.BusNameWatcherFlags.NONE,
            null, () => dialog.cancel());
        dialog.show(pending.observation, language);
    }

    CloseAuthorizedWindow(generation) {
        // KYRIN owns persistent consent. Shell owns atomic target validation.
        return this._commitWindowClose(generation, false);
    }

    CloseConfirmedWindow(generation) {
        return this._commitWindowClose(generation, true);
    }

    _commitWindowClose(generation, requireConfirmation) {
        const pending = this._pendingClose;
        this._pendingClose = null; // Invalid, expired and repeated commits burn it.
        this._closeDialog?.cancel();
        if (!pending || generation !== pending.observation.generation ||
            GLib.get_monotonic_time() / 1000000 >= pending.observation.deadline ||
            global.display.get_focus_window() !== pending.focus ||
            (pending.number > 0 && pending.snapshot !==
                (pending.appId === '' ? this._shownOpen : this._shownWindows)))
            return 'stale';
        if (requireConfirmation && !pending.approved)
            return 'confirmation_required';
        const fresh = this._closeCandidate(pending.appId, pending.number);
        const wanted = pending.observation;
        if (!fresh || fresh.window !== pending.window || fresh.appId !== wanted.app_id ||
            fresh.window.get_pid() !== wanted.process_id ||
            String(fresh.window.get_stable_sequence()) !== wanted.window_token)
            return 'stale';
        if (!fresh.window.can_close())
            return 'unavailable';
        const timestamp = global.display.get_current_time_roundtrip();
        if (GLib.get_monotonic_time() / 1000000 >= wanted.deadline ||
            global.display.get_focus_window() !== pending.focus)
            return 'stale';
        this._clearPicker();
        // Normal WM close only: no kill, save/discard response or retry.
        fresh.window.delete(timestamp);
        return 'requested';
    }

    ControlAppWindow(appId, operation) {
        if (operation === 'close')
            return ['confirmation_required', ''];
        if (![
            'restore', 'minimize', 'maximize', 'unmaximize',
            'fullscreen', 'unfullscreen',
        ].includes(operation))
            return ['unknown', ''];
        const windows = this._appWindows(appId);
        if (windows === null)
            return ['unknown', ''];
        if (windows.length === 0)
            return ['no_window', ''];
        const focused = global.display.get_focus_window();
        const window = windows.length === 1
            ? windows[0]
            : windows.includes(focused) &&
              Shell.WindowTracker.get_default().get_window_app(focused)?.get_id() === appId
                ? focused : null;
        if (window === null)
            return ['multiple_windows', ''];
        if ((operation === 'minimize' && !window.can_minimize()) ||
            (operation === 'maximize' && !window.can_maximize()))
            return ['unavailable', ''];
        const token = String(window.get_stable_sequence());
        if (operation === 'restore')
            Main.activateWindow(window, global.display.get_current_time_roundtrip());
        else if (operation === 'minimize')
            window.minimize();
        else {
            if (operation === 'maximize')
                window.maximize();
            else if (operation === 'unmaximize') {
                if (window.is_fullscreen())
                    window.unmake_fullscreen();
                window.unmaximize();
            } else if (operation === 'fullscreen')
                window.make_fullscreen();
            else
                window.unmake_fullscreen();
            Main.activateWindow(window, global.display.get_current_time_roundtrip());
        }
        return ['requested', token];
    }
}
