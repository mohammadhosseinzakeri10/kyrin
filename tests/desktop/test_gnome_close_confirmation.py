"""The native confirmation has bounded lifetime and requires its own button."""

import shutil
import subprocess
from pathlib import Path

import pytest

_SOURCE = (
    Path(__file__).resolve().parents[2]
    / "integrations/gnome-shell/active-app@kyrin.local/closeConfirmation.js"
)
_HARNESS = """
let now = 1000000;
let callback = null;
let timerMs = null;
let instances = [];
let canOpen = true;
const GLib = {
    PRIORITY_DEFAULT: 0,
    get_monotonic_time: () => now,
    timeout_add_once: (_priority, ms, f) => { callback = f; timerMs = ms; return 1; },
    source_remove: () => { callback = null; },
};
const Clutter = {KEY_Escape: 27, TextDirection: {RTL: 1, LTR: 0}};
const St = {Label: class {
    constructor(props) { this.text = props.text; this.clutter_text = {}; }
    set_text_direction(direction) { this.direction = direction; }
}};
const ModalDialog = {ModalDialog: class {
    constructor() {
        instances.push(this);
        this.children = [];
        this.contentLayout = {add_child: label => this.children.push(label)};
        this.destroyed = false;
        this.opened = false;
    }
    set_text_direction(direction) { this.direction = direction; }
    setButtons(buttons) { this.buttons = buttons; }
    connect(_signal, handler) { this.onDestroy = handler; }
    open() { this.opened = canOpen; return canOpen; }
    close() { if (this.opened) this.destroy(); }
    destroy() {
        if (this.destroyed) throw new Error('dialog destroyed twice');
        this.destroyed = true;
        this.onDestroy();
    }
}};
"""


@pytest.mark.parametrize(
    "case", ["approve", "cancel", "timeout", "destroy", "no_grab", "expired"]
)
@pytest.mark.parametrize("language", ["en", "fa"])
def test_native_dialog_button_deadline_and_cleanup(case: str, language: str) -> None:
    gjs = shutil.which("gjs")
    if gjs is None:
        pytest.skip("GJS is not installed")
    source = "\n".join(
        line
        for line in _SOURCE.read_text().splitlines()
        if not line.startswith("import ")
    ).replace("export class", "class")
    body = """
        const results = [];
        const confirmation = new WindowCloseConfirmation(value => results.push(value));
        const observation = {app_id: 'test.desktop', window_token: '17', deadline: 11};
        SETUP
        confirmation.show(observation, 'LANGUAGE');
        const dialog = instances[0];
        if (dialog) {
            if (dialog.direction !== DIRECTION)
                throw new Error('incorrect writing direction');
            if (!dialog.children[0].text.includes('test.desktop'))
                throw new Error('missing target');
            if (timerMs !== 10000) throw new Error('deadline extended');
        }
        ACTION
        confirmation.cancel(); // Late cancellation must not publish a second result.
        if (callback !== null || confirmation._dialog !== null || results.length !== 1
            || results[0] !== EXPECTED || (dialog && !dialog.destroyed))
            throw new Error('dialog leaked or returned an incorrect decision');
    """
    setup = (
        "now = 11000000;"
        if case == "expired"
        else "canOpen = false;"
        if case == "no_grab"
        else ""
    )
    action = {
        "approve": "dialog.buttons[1].action();",
        "cancel": "dialog.buttons[0].action();",
        "timeout": "now = 11000000; const fire = callback; callback = null; fire();",
        "destroy": "dialog.destroy();",
        "no_grab": "",
        "expired": "",
    }[case]
    body = body.replace("SETUP", setup).replace("ACTION", action)
    body = body.replace("LANGUAGE", language).replace(
        "DIRECTION", "1" if language == "fa" else "0"
    )
    body = body.replace("EXPECTED", "true" if case == "approve" else "false")
    result = subprocess.run(
        [gjs, "-c", _HARNESS + source + body],
        capture_output=True,
        text=True,
        check=False,
        timeout=5,
    )
    assert result.returncode == 0, result.stderr
