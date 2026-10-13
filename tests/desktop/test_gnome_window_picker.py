"""Exercise the GNOME picker layout without touching the live desktop."""

import shutil
import subprocess
from pathlib import Path

import pytest

_PICKER = (
    Path(__file__).resolve().parents[2]
    / "integrations/gnome-shell/active-app@kyrin.local/windowPicker.js"
)

_HARNESS = """
const cards = [];
const images = [];
class Actor {
    constructor(options = {}) {
        Object.assign(this, options);
        this.children = [];
        if (options.clip_to_allocation) images.push(this);
    }
    add_child(child) { this.children.push(child); }
    set_child(child) { this.child = child; }
    set_position(x, y) { this.x = x; this.y = y; }
    set_size(width, height) { this.width = width; this.height = height; }
    connect(name, callback) { this[name] = callback; }
    grab_key_focus() {}
    destroy() { this.destroyed = true; }
}
const St = {
    Widget: Actor, BoxLayout: Actor, Label: Actor, ScrollView: Actor,
    Button: class extends Actor {
        constructor(options) { super(options); cards.push(this); }
    },
    PolicyType: {NEVER: 0, AUTOMATIC: 1},
};
const Clutter = {
    FixedLayout: class {}, Clone: Actor, KEY_Escape: 9,
    EVENT_STOP: true, EVENT_PROPAGATE: false,
};
let popped = 0;
const Main = {
    uiGroup: new Actor(),
    pushModal: () => ({}),
    popModal: () => { popped++; },
};
const global = {stage: {width: 1200, height: 800}};
"""

_CASES = """
const selected = [];
let dismissed = false;
const picker = new WindowPicker(number => selected.push(number), () => {
    dismissed = true;
});
const windows = [1, 2, 3, 4].map(number => ({
    get_compositor_private: () => ({number}),
    get_frame_rect: () => ({width: 800, height: 600}),
}));
if (!picker.show(windows, ['Telegram', 'Terminal', 'Firefox', 'Code'],
    'Open windows') || cards.length !== 4 || images.length !== 4)
    throw new Error('expected exactly four previews');
if (cards[0].child.children[0].text !== '1. Telegram'
    || cards[2].child.children[0].text !== '3. Firefox')
    throw new Error('app labels do not match the numbered previews');
if (!images.every(image => image.width === images[0].width
    && image.height === images[0].height))
    throw new Error('previews do not have equal sizes');
cards[2].clicked();
if (selected.join(',') !== '3') throw new Error('wrong numbered preview selected');
Main.uiGroup.children[0]['key-press-event'](null, {get_key_symbol: () => 9});
if (!dismissed) throw new Error('Escape did not dismiss the picker');
picker.destroy();
if (popped !== 1) throw new Error('modal input was not released');
print('GNOME picker: passed');
"""


def test_picker_shows_equal_previews_and_clicks_the_numbered_window() -> None:
    gjs = shutil.which("gjs")
    if gjs is None:
        pytest.skip("GJS is not installed")
    source = "\n".join(
        line
        for line in _PICKER.read_text(encoding="utf-8").splitlines()
        if not line.startswith("import ")
    ).replace("export class WindowPicker", "class WindowPicker")
    result = subprocess.run(
        [gjs, "-c", _HARNESS + source + _CASES],
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )
    assert result.returncode == 0, result.stderr
    assert "GNOME picker: passed" in result.stdout
