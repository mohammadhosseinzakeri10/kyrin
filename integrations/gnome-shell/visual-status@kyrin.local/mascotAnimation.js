import Clutter from 'gi://Clutter';
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';

// Only compositor properties move. Audio and command workers never render frames.
const NEUTRAL = {
    translation_x: 0,
    translation_y: 0,
    rotation_angle_z: 0,
    scale_x: 1,
    scale_y: 1,
    opacity: 255,
};

const REACTIONS = {
    ready: {
        repeat: true,
        frames: [
            {duration: 1100, body: {translation_y: -1},
                head: {translation_y: -1}},
            {duration: 1100},
        ],
    },
    conversation: {
        repeat: false,
        frames: [
            {duration: 220, head: {rotation_angle_z: 5},
                rightArm: {rotation_angle_z: 42}},
            {duration: 180, rightArm: {rotation_angle_z: 20}},
            {duration: 180, rightArm: {rotation_angle_z: 42}},
            {duration: 260},
        ],
    },
    listening: {
        repeat: true,
        frames: [
            {duration: 500, head: {rotation_angle_z: -5, translation_y: -2},
                leftArm: {rotation_angle_z: -12}, rightArm: {rotation_angle_z: 9},
                eyes: {scale_x: 1.08}},
            {duration: 100, head: {rotation_angle_z: -5, translation_y: -2},
                leftArm: {rotation_angle_z: -12}, rightArm: {rotation_angle_z: 9},
                eyes: {scale_y: 0.14}},
            {duration: 550, head: {rotation_angle_z: 5},
                leftArm: {rotation_angle_z: 8}, rightArm: {rotation_angle_z: -12}},
            {duration: 900, body: {translation_y: 1}},
        ],
    },
    processing: {
        repeat: true,
        frames: [
            {duration: 650, head: {rotation_angle_z: 8, translation_y: -2},
                leftArm: {rotation_angle_z: -28}, eyes: {scale_y: 0.75},
                body: {translation_y: -2}},
            {duration: 650, head: {rotation_angle_z: -7},
                rightArm: {rotation_angle_z: 28}, eyes: {scale_y: 0.9}},
        ],
    },
    question: {
        repeat: true,
        mark: '?',
        frames: [
            {duration: 600, head: {rotation_angle_z: -13},
                leftArm: {rotation_angle_z: -22}, rightArm: {rotation_angle_z: 22}},
            {duration: 850, head: {rotation_angle_z: -7},
                leftArm: {rotation_angle_z: -14}, rightArm: {rotation_angle_z: 14}},
        ],
    },
    executing: {
        repeat: true,
        frames: [
            {duration: 240, body: {translation_y: -5},
                head: {translation_y: -3, rotation_angle_z: -3},
                leftLeg: {rotation_angle_z: 18, translation_y: -3},
                rightLeg: {rotation_angle_z: -18},
                leftArm: {rotation_angle_z: -24},
                rightArm: {rotation_angle_z: 24}},
            {duration: 240, body: {translation_y: 0},
                head: {rotation_angle_z: 3},
                leftLeg: {rotation_angle_z: -18},
                rightLeg: {rotation_angle_z: 18, translation_y: -3},
                leftArm: {rotation_angle_z: 24},
                rightArm: {rotation_angle_z: -24}},
        ],
    },
    confirmed: {
        repeat: false,
        mark: '✓',
        frames: [
            {duration: 220, body: {translation_y: -9},
                head: {translation_y: -7},
                leftArm: {rotation_angle_z: -42},
                rightArm: {rotation_angle_z: 42}},
            {duration: 300},
        ],
    },
    unverified: {
        repeat: true,
        mark: '…',
        frames: [
            {duration: 700, body: {translation_y: -2},
                head: {rotation_angle_z: 4}},
            {duration: 700, head: {rotation_angle_z: -4}},
        ],
    },
    failed: {
        repeat: false,
        mark: '!',
        frames: [
            {duration: 250, body: {translation_y: 3},
                head: {rotation_angle_z: 11},
                leftArm: {rotation_angle_z: 15},
                rightArm: {rotation_angle_z: -15},
                eyes: {scale_y: 0.55}},
            {duration: 350, body: {translation_y: 2},
                head: {rotation_angle_z: 7}, eyes: {scale_y: 0.7}},
        ],
    },
};

const PIVOTS = {
    leftLeg: [0.40, 0.72],
    rightLeg: [0.60, 0.72],
    leftArm: [0.32, 0.51],
    rightArm: [0.68, 0.51],
    body: [0.5, 0.7],
    head: [0.5, 0.49],
    eyes: [0.5, 0.33],
};

export class MascotAnimator {
    constructor(parts, symbol) {
        this._parts = parts;
        this._symbol = symbol;
        for (const [name, actor] of Object.entries(parts))
            actor.set_pivot_point(...PIVOTS[name]);
        this._status = null;
        this._active = true;
        this._generation = 0;
        this._frameTimeoutId = 0;
        this._motionSettings = new Gio.Settings({schema_id: 'org.gnome.desktop.interface'});
        this._settingsId = this._motionSettings.connect(
            'changed::enable-animations', () => this._restart());
    }

    setStatus(status) {
        if (this._status === status)
            return;
        this._status = status;
        this._restart();
    }

    setVisible(visible) {
        if (this._active === visible)
            return;
        this._active = visible;
        this._restart();
    }

    _restart() {
        this._generation++;
        this._cancelFrameTimeout();
        for (const actor of Object.values(this._parts)) {
            actor.remove_all_transitions();
            Object.assign(actor, NEUTRAL);
        }
        const reaction = REACTIONS[this._status];
        if (reaction?.mark) {
            this._symbol.text = reaction.mark;
            this._symbol.set_style_class_name(
                `kyrin-status-symbol kyrin-status-symbol-${this._status}`);
            this._symbol.show();
        } else {
            this._symbol.hide();
        }
        if (this._active && this._motionSettings.get_boolean('enable-animations'))
            this._next(this._generation, 0);
    }

    _next(generation, frameIndex) {
        if (generation !== this._generation || !this._active)
            return;
        const reaction = REACTIONS[this._status];
        if (!reaction || frameIndex >= reaction.frames.length)
            return;
        const frame = reaction.frames[frameIndex];
        for (const [name, actor] of Object.entries(this._parts)) {
            actor.ease({
                ...NEUTRAL,
                ...frame[name],
                duration: frame.duration,
                mode: Clutter.AnimationMode.EASE_IN_OUT_SINE,
            });
        }
        this._frameTimeoutId = GLib.timeout_add(GLib.PRIORITY_DEFAULT,
            frame.duration, () => {
                this._frameTimeoutId = 0;
                if (generation !== this._generation)
                    return GLib.SOURCE_REMOVE;
                const next = frameIndex + 1;
                if (next < reaction.frames.length)
                    this._next(generation, next);
                else if (reaction.repeat)
                    this._next(generation, 0);
                return GLib.SOURCE_REMOVE;
            });
    }

    _cancelFrameTimeout() {
        if (this._frameTimeoutId)
            GLib.source_remove(this._frameTimeoutId);
        this._frameTimeoutId = 0;
    }

    destroy() {
        this._generation++;
        this._cancelFrameTimeout();
        for (const actor of Object.values(this._parts))
            actor.remove_all_transitions();
        this._motionSettings.disconnect(this._settingsId);
        this._parts = null;
        this._symbol = null;
        this._motionSettings = null;
    }
}
