import Clutter from 'gi://Clutter';
import GLib from 'gi://GLib';
import St from 'gi://St';

import * as ModalDialog from 'resource:///org/gnome/shell/ui/modalDialog.js';

// Shell actors do not create a second Meta.Window. A Qt top-level on Wayland
// can take focus despite its no-focus hint, invalidating the prepared close.
export class WindowCloseConfirmation {
    constructor(done) {
        this._done = done;
        this._dialog = null;
        this._timer = null;
        this._finished = false;
    }

    show(observation, language) {
        const remaining = observation.deadline - GLib.get_monotonic_time() / 1000000;
        if (remaining <= 0) {
            this.cancel();
            return;
        }
        const persian = language.split('-')[0] === 'fa';
        const dialog = new ModalDialog.ModalDialog({
            shouldFadeIn: false,
            shouldFadeOut: false,
        });
        this._dialog = dialog;
        dialog.set_text_direction(persian ? Clutter.TextDirection.RTL : Clutter.TextDirection.LTR);
        const text = persian
            ? `بستن معمول پنجره\nبرنامه: ${observation.app_id}\nپنجره: ${observation.window_token}\n`
                + 'ممکن است کار ذخیره‌نشده یا فرایند در حال اجرا از دست برود. '
                + 'پرسش ذخیره‌سازی خود برنامه پاسخ داده نمی‌شود. فقط همین عمل را تأیید می‌کنید.'
            : `Normal window close\nApp: ${observation.app_id}\nWindow: ${observation.window_token}\n`
                + "Unsaved work or running jobs may be lost. The application's own save dialog "
                + 'will not be answered. Approve only this operation, once.';
        const label = new St.Label({text, style: 'max-width: 620px;'});
        label.clutter_text.line_wrap = true;
        label.set_text_direction(persian ? Clutter.TextDirection.RTL : Clutter.TextDirection.LTR);
        dialog.contentLayout.add_child(label);
        dialog.setButtons([
            {label: persian ? 'لغو' : 'Cancel', key: Clutter.KEY_Escape,
                action: () => this.cancel()},
            {label: persian ? 'تأیید همین عمل' : 'Approve this operation',
                action: () => this._finish(true)},
        ]);
        dialog.connect('destroy', () => {
            if (this._dialog === dialog)
                this._dialog = null;
            this._finish(false);
        });
        this._timer = GLib.timeout_add_once(GLib.PRIORITY_DEFAULT,
            Math.max(1, Math.ceil(remaining * 1000)), () => {
                this._timer = null;
                this.cancel();
            });
        if (!dialog.open())
            dialog.destroy();
    }

    cancel() {
        this._finish(false);
    }

    _finish(approved) {
        if (this._finished)
            return;
        this._finished = true;
        if (this._timer !== null)
            GLib.source_remove(this._timer);
        this._timer = null;
        const dialog = this._dialog;
        this._dialog = null;
        dialog?.close();
        // The extension rechecks the original deadline, generation and focus.
        this._done(approved);
    }
}
