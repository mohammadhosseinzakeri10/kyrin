import Gio from 'gi://Gio';
import Shell from 'gi://Shell';

import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';

const INTERFACE_XML = `<node>
  <interface name="org.kyrin.ActiveApp">
    <method name="GetActiveApp">
      <arg name="app_id" type="s" direction="out"/>
    </method>
    <method name="GetActiveWindow">
      <arg name="app_id" type="s" direction="out"/>
      <arg name="pid" type="u" direction="out"/>
    </method>
    <method name="ActivateExistingApp">
      <arg name="app_id" type="s" direction="in"/>
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
    enable() {
        this._dbusObject = Gio.DBusExportedObject.wrapJSObject(INTERFACE_XML, this);
        this._dbusObject.export(Gio.DBus.session, '/org/kyrin/ActiveApp');
    }

    disable() {
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

    ControlAppWindow(appId, operation) {
        if (![
            'restore', 'minimize', 'close', 'maximize', 'unmaximize',
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
            (operation === 'maximize' && !window.can_maximize()) ||
            (operation === 'close' && !window.can_close()))
            return ['unavailable', ''];
        const token = String(window.get_stable_sequence());
        if (operation === 'restore')
            Main.activateWindow(window, global.display.get_current_time_roundtrip());
        else if (operation === 'minimize')
            window.minimize();
        else if (operation === 'close')
            window.delete(global.display.get_current_time_roundtrip());
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
