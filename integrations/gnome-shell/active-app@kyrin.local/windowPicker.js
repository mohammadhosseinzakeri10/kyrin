import Clutter from 'gi://Clutter';
import St from 'gi://St';

import * as Main from 'resource:///org/gnome/shell/ui/main.js';

// This is a temporary, application-scoped chooser. It never changes the real
// window sizes or stores screenshots; clones refer to live window actors.
export class WindowPicker {
    constructor(onSelect, onDismiss) {
        this._onSelect = onSelect;
        this._onDismiss = onDismiss;
        this._root = null;
        this._grab = null;
    }

    show(windows, names = null, title = 'Terminal windows — say a number or click a preview') {
        this.destroy();
        const width = global.stage.width;
        const height = global.stage.height;
        const columns = Math.min(windows.length, 4);
        const rows = Math.ceil(windows.length / columns);
        const tileWidth = Math.max(170, Math.min(350, (width - 80) / columns - 18));
        const tileHeight = Math.max(130, Math.min(260, (height - 100) / rows - 18));
        const root = new St.Widget({
            reactive: true,
            can_focus: true,
            layout_manager: new Clutter.FixedLayout(),
            style: 'background-color: rgba(5, 9, 22, 0.87);',
        });
        root.set_position(0, 0);
        root.set_size(width, height);
        const grid = new St.BoxLayout({vertical: true, style: 'spacing: 16px;'});
        const heading = new St.Label({
            text: title,
            style: 'color: white; font-size: 19px; font-weight: bold;',
        });
        grid.add_child(heading);
        for (let row = 0; row < rows; row++) {
            const line = new St.BoxLayout({style: 'spacing: 16px;'});
            for (let column = 0; column < columns; column++) {
                const index = row * columns + column;
                if (index >= windows.length)
                    break;
                const window = windows[index];
                const card = new St.Button({
                    reactive: true,
                    can_focus: true,
                    style: 'background-color: #18223d; border: 2px solid #7389d8; '
                        + 'border-radius: 12px; padding: 8px;',
                });
                const content = new St.BoxLayout({vertical: true, style: 'spacing: 7px;'});
                content.add_child(new St.Label({
                    text: `${index + 1}. ${names?.[index] ?? 'Terminal'}`,
                    style: 'color: white; font-size: 16px; font-weight: bold;',
                }));
                const image = new St.Widget({
                    width: tileWidth - 20,
                    height: tileHeight - 48,
                    clip_to_allocation: true,
                    style: 'background-color: #0b1022;',
                });
                const actor = window.get_compositor_private();
                if (actor) {
                    const rect = window.get_frame_rect();
                    const scale = Math.min(
                        image.width / Math.max(rect.width, 1),
                        image.height / Math.max(rect.height, 1)
                    );
                    image.add_child(new Clutter.Clone({
                        source: actor,
                        width: rect.width * scale,
                        height: rect.height * scale,
                    }));
                }
                content.add_child(image);
                card.set_child(content);
                card.connect('clicked', () => this._onSelect(index + 1));
                line.add_child(card);
            }
            grid.add_child(line);
        }
        const chooserWidth = Math.min(width - 24, columns * (tileWidth + 18) + 20);
        const chooserHeight = Math.min(height - 48, 45 + rows * (tileHeight + 18));
        const scroller = new St.ScrollView({
            width: chooserWidth,
            height: chooserHeight,
            hscrollbar_policy: St.PolicyType.NEVER,
            vscrollbar_policy: St.PolicyType.AUTOMATIC,
            enable_mouse_scrolling: true,
            child: grid,
        });
        root.add_child(scroller);
        scroller.set_position(
            Math.max(12, (width - chooserWidth) / 2),
            Math.max(12, (height - chooserHeight) / 2)
        );
        root.connect('key-press-event', (_actor, event) => {
            if (event.get_key_symbol() === Clutter.KEY_Escape) {
                this._onDismiss();
                return Clutter.EVENT_STOP;
            }
            return Clutter.EVENT_PROPAGATE;
        });
        Main.uiGroup.add_child(root);
        this._root = root;
        this._grab = Main.pushModal(root);
        if (this._grab === null) {
            this.destroy();
            return false;
        }
        root.grab_key_focus();
        return true;
    }

    destroy() {
        if (this._grab !== null) {
            Main.popModal(this._grab);
            this._grab = null;
        }
        this._root?.destroy();
        this._root = null;
    }
}
