import Clutter from 'gi://Clutter';
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import Meta from 'gi://Meta';
import Pango from 'gi://Pango';
import St from 'gi://St';

import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import * as PanelMenu from 'resource:///org/gnome/shell/ui/panelMenu.js';
import * as PopupMenu from 'resource:///org/gnome/shell/ui/popupMenu.js';
import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';
import {MascotAnimator} from './mascotAnimation.js';

const INTERFACE_XML = `<node>
  <interface name="org.kyrin.VisualStatus">
    <method name="GetCapabilities">
      <arg name="manifest" type="s" direction="out"/>
    </method>
    <method name="SetStatus">
      <arg name="status" type="s" direction="in"/>
    </method>
    <method name="SetPresentation">
      <arg name="status" type="s" direction="in"/>
      <arg name="caption" type="s" direction="in"/>
    </method>
  </interface>
</node>`;

const STATES = {
    ready: ['Ready to listen…', 'KYRIN is ready for speech'],
    conversation: ['Responding…', 'KYRIN is responding to the user'],
    listening: ['Listening…', 'KYRIN is listening'],
    processing: ['Understanding speech…', 'KYRIN is processing speech'],
    question: ['Please clarify…', 'KYRIN needs an answer'],
    executing: ['Working…', 'KYRIN is carrying out an action'],
    confirmed: ['Done.', 'Action confirmed'],
    unverified: ['Request sent; checking…', 'Action requested; result not confirmed'],
    failed: ['Could not complete that.', 'Action failed or was blocked'],
};

export default class KyrinVisualStatusExtension extends Extension {
    // This literal belongs to the loaded module; metadata on disk may be newer.
    GetCapabilities() {
        return JSON.stringify({"protocol_version": 1, "build_id": "visual-status@kyrin.local-2026-10-24-f20", "capabilities": ["SetStatus", "SetPresentation"]});
    }

    enable() {
        const layer = name => {
            const actor = new St.Icon({
                gicon: new Gio.FileIcon({
                    file: Gio.File.new_for_path(`${this.path}/mascot${name}.svg`),
                }),
                icon_size: 112,
            });
            actor.set_position(0, 0);
            return actor;
        };
        this._mascot = new St.Widget({
            layout_manager: new Clutter.FixedLayout(),
            width: 112,
            height: 112,
            style_class: 'kyrin-status-icon',
        });
        const parts = {
            leftLeg: layer('LeftLeg'),
            rightLeg: layer('RightLeg'),
            leftArm: layer('LeftArm'),
            rightArm: layer('RightArm'),
            body: layer('Body'),
            head: new St.Widget({
                layout_manager: new Clutter.FixedLayout(),
                width: 112,
                height: 112,
            }),
            eyes: layer('Eyes'),
        };
        for (const name of ['leftLeg', 'rightLeg', 'leftArm', 'rightArm', 'body'])
            this._mascot.add_child(parts[name]);
        parts.head.add_child(layer('Head'));
        parts.head.add_child(parts.eyes);
        this._mascot.add_child(parts.head);
        this._statusSymbol = new St.Label({
            style_class: 'kyrin-status-symbol',
            x: 83,
            y: 1,
        });
        this._statusSymbol.hide();
        this._mascot.add_child(this._statusSymbol);
        this._caption = new St.Label({
            text: STATES.ready[0],
            style_class: 'kyrin-status-caption',
            x_align: Clutter.ActorAlign.CENTER,
        });
        this._caption.clutter_text.line_wrap = true;
        this._caption.clutter_text.line_wrap_mode = Pango.WrapMode.WORD_CHAR;
        this._caption.clutter_text.ellipsize = Pango.EllipsizeMode.NONE;
        this._content = new St.BoxLayout({
            vertical: true,
            reactive: true,
            style_class: 'kyrin-status-content',
        });
        this._mascotRow = new St.Widget({
            layout_manager: new Clutter.FixedLayout(),
            width: 112,
            height: 112,
        });
        this._mascotRow.add_child(this._mascot);
        this._content.add_child(this._mascotRow);
        this._content.add_child(this._caption);
        this._closeButton = new St.Button({
            label: '×',
            style_class: 'kyrin-status-close',
            x_align: Clutter.ActorAlign.END,
            can_focus: true,
            reactive: true,
            track_hover: true,
        });
        this._closeButton.set_accessible_name('Hide KYRIN character');
        this._closeHint = new St.Label({
            text: 'Hide KYRIN',
            style_class: 'kyrin-status-tooltip',
            y_align: Clutter.ActorAlign.CENTER,
        });
        this._closeHint.hide();
        this._closeRow = new St.BoxLayout({
            x_align: Clutter.ActorAlign.END,
            style_class: 'kyrin-status-close-row',
        });
        this._closeRow.add_child(this._closeHint);
        this._closeRow.add_child(this._closeButton);
        this._actor = new St.BoxLayout({
            vertical: true,
            reactive: true,
            style_class: 'kyrin-status',
        });
        this._actor.add_child(this._closeRow);
        this._actor.add_child(this._content);
        this._audioButton = new St.Button({
            label: 'Paste audio',
            style_class: 'kyrin-audio-import',
            x_align: Clutter.ActorAlign.CENTER,
            can_focus: true,
            reactive: true,
            track_hover: true,
        });
        this._audioButton.set_accessible_name('Paste an audio file into KYRIN');
        this._actor.add_child(this._audioButton);
        this._audioButtonId = this._audioButton.connect('clicked', () => {
            try {
                const path = GLib.build_filenamev([
                    GLib.get_user_runtime_dir(), 'kyrin-control.sock',
                ]);
                const client = new Gio.SocketClient();
                client.set_timeout(1);
                const connection = client.connect(
                    new Gio.UnixSocketAddress({path}), null);
                connection.get_output_stream().write_all(
                    new TextEncoder().encode('paste-audio\n'), null);
                connection.close(null);
            } catch (error) {
                console.warn(`KYRIN audio paste request failed: ${error}`);
            }
        });
        this._actor.set_accessible_name(STATES.ready[1]);
        const monitor = Main.layoutManager.primaryMonitor;
        this._actor.set_position(monitor.x + monitor.width - 175, monitor.y + 55);
        Main.layoutManager.addChrome(this._actor, {trackFullscreen: false});
        this._resizeCaption();
        this._keepOnMonitor();
        this._closeHoverId = this._closeButton.connect('notify::hover', () => {
            if (this._closeButton.hover)
                this._closeHint.show();
            else
                this._closeHint.hide();
        });
        this._closePressId = this._closeButton.connect('button-press-event',
            (_button, event) => {
                if (event.get_button() !== 1)
                    return Clutter.EVENT_PROPAGATE;
                this._hideCharacter();
                return Clutter.EVENT_STOP;
            });
        this._closeId = this._closeButton.connect('clicked', () => this._hideCharacter());
        this._panelButton = new PanelMenu.Button(0.0, 'KYRIN character');
        this._panelButton.add_child(new St.Label({text: 'KYRIN'}));
        const showItem = new PopupMenu.PopupMenuItem('Show KYRIN character');
        showItem.connect('activate', () => this._showCharacter());
        this._panelButton.menu.addMenuItem(showItem);
        Main.panel.addToStatusArea('kyrin-visual-status', this._panelButton);
        this._panelButton.hide();
        this._animator = new MascotAnimator(parts, this._statusSymbol);
        this._animator.setStatus('ready');

        // GNOME Shell 50 no longer exposes Clutter.DragAction. Track only a
        // primary-button drag begun on this actor and keep it on the monitor.
        this._dragOrigin = null;
        this._pendingPosition = null;
        this._motionLaterId = 0;
        this._pressId = this._content.connect('button-press-event', (_actor, event) =>
            this._beginDrag(event));
        this._stageId = global.stage.connect('captured-event', (_stage, event) => {
            if (!this._dragOrigin)
                return Clutter.EVENT_PROPAGATE;
            if (event.type() === Clutter.EventType.BUTTON_RELEASE) {
                const [pointerX, pointerY] = event.get_coords();
                this._moveDrag(pointerX, pointerY);
                this._dragOrigin = null;
                if (this._motionLaterId)
                    global.compositor.get_laters().remove(this._motionLaterId);
                this._motionLaterId = 0;
                this._flushDragPosition();
                return Clutter.EVENT_STOP;
            }
            if (event.type() !== Clutter.EventType.MOTION)
                return Clutter.EVENT_PROPAGATE;
            const [pointerX, pointerY] = event.get_coords();
            this._moveDrag(pointerX, pointerY);
            return Clutter.EVENT_STOP;
        });

        this._dbusObject = Gio.DBusExportedObject.wrapJSObject(INTERFACE_XML, this);
        this._dbusObject.export(Gio.DBus.session, '/org/kyrin/VisualStatus');
    }

    _beginDrag(event) {
        if (event.get_button() !== 1)
            return Clutter.EVENT_PROPAGATE;
        const [pointerX, pointerY] = event.get_coords();
        this._dragOrigin = [pointerX, pointerY, this._actor.x, this._actor.y];
        return Clutter.EVENT_STOP;
    }

    _moveDrag(pointerX, pointerY) {
        const [startX, startY, actorX, actorY] = this._dragOrigin;
        const area = Main.layoutManager.primaryMonitor;
        const x = Math.max(area.x, Math.min(actorX + pointerX - startX,
            area.x + area.width - this._actor.width));
        const y = Math.max(area.y, Math.min(actorY + pointerY - startY,
            area.y + area.height - this._actor.height));
        this._queueDragPosition(x, y);
    }

    _queueDragPosition(x, y) {
        this._pendingPosition = [x, y];
        if (this._motionLaterId)
            return;
        this._motionLaterId = global.compositor.get_laters().add(
            Meta.LaterType.BEFORE_REDRAW, () => {
                this._motionLaterId = 0;
                this._flushDragPosition();
                return GLib.SOURCE_REMOVE;
            });
    }

    _flushDragPosition() {
        const position = this._pendingPosition;
        this._pendingPosition = null;
        if (position && this._actor)
            this._actor.set_position(...position);
    }

    _resizeCaption() {
        const monitor = Main.layoutManager.primaryMonitor;
        const [, textWidth] = this._caption.clutter_text.get_preferred_width(-1);
        const maxWidth = Math.max(112, Math.min(360, monitor.width - 24));
        // Leave room for the caption's CSS padding and border.
        this._caption.width = Math.min(maxWidth, Math.max(112, Math.ceil(textWidth) + 14));
        this._mascotRow.width = this._caption.width;
        this._mascot.set_position(
            Math.floor((this._mascotRow.width - this._mascot.width) / 2), 0);
    }

    _keepOnMonitor() {
        const monitor = Main.layoutManager.primaryMonitor;
        const [, width] = this._actor.get_preferred_width(-1);
        const [, height] = this._actor.get_preferred_height(width);
        this._actor.set_position(
            Math.max(monitor.x, Math.min(this._actor.x, monitor.x + monitor.width - width)),
            Math.max(monitor.y, Math.min(this._actor.y, monitor.y + monitor.height - height))
        );
    }

    SetStatus(status) {
        if (STATES[status])
            this.SetPresentation(status, STATES[status][0]);
    }

    SetPresentation(status, caption) {
        const state = STATES[status];
        if (!state)
            return;
        const visibleCaption = caption.replace(/\s+/g, ' ').trim();
        this._caption.text = visibleCaption || state[0];
        this._resizeCaption();
        this._keepOnMonitor();
        this._actor.set_accessible_name(state[1]);
        this._animator.setStatus(status);
    }

    _hideCharacter() {
        this._dragOrigin = null;
        this._closeHint.hide();
        this._actor.hide();
        this._animator.setVisible(false);
        this._panelButton.show();
    }

    _showCharacter() {
        this._panelButton.hide();
        this._actor.show();
        this._animator.setVisible(true);
    }

    disable() {
        this._animator?.destroy();
        this._animator = null;
        if (this._motionLaterId)
            global.compositor.get_laters().remove(this._motionLaterId);
        this._motionLaterId = 0;
        this._pendingPosition = null;
        if (this._stageId)
            global.stage.disconnect(this._stageId);
        this._stageId = 0;
        if (this._pressId && this._content)
            this._content.disconnect(this._pressId);
        this._pressId = 0;
        if (this._closeHoverId && this._closeButton)
            this._closeButton.disconnect(this._closeHoverId);
        this._closeHoverId = 0;
        if (this._closePressId && this._closeButton)
            this._closeButton.disconnect(this._closePressId);
        this._closePressId = 0;
        if (this._closeId && this._closeButton)
            this._closeButton.disconnect(this._closeId);
        this._closeId = 0;
        if (this._audioButtonId && this._audioButton)
            this._audioButton.disconnect(this._audioButtonId);
        this._audioButtonId = 0;
        this._dragOrigin = null;
        this._dbusObject?.unexport();
        this._dbusObject = null;
        this._panelButton?.destroy();
        this._panelButton = null;
        this._actor?.destroy();
        this._actor = null;
        this._content = null;
        this._mascotRow = null;
        this._mascot = null;
        this._statusSymbol = null;
        this._caption = null;
        this._closeRow = null;
        this._closeHint = null;
        this._closeButton = null;
        this._audioButton = null;
    }
}
