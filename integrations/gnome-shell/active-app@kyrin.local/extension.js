import Gio from 'gi://Gio';
import Shell from 'gi://Shell';

import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';

const INTERFACE_XML = `<node>
  <interface name="org.kyrin.ActiveApp">
    <method name="GetActiveApp">
      <arg name="app_id" type="s" direction="out"/>
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
}
