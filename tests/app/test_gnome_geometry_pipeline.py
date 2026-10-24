"""Run actual GJS metadata through Qt crop/OCR and both pointer actuators.

Shell acquisition, OCR recognition and portal transport are deterministic fakes;
metadata production, PNG processing, target resolution and input guards are real.
"""

# ruff: noqa: E402

import json
import shutil
import subprocess
from pathlib import Path
from types import ModuleType

import pytest

pytest.importorskip("PySide6")
from PySide6.QtCore import QBuffer, QByteArray, QIODevice
from PySide6.QtGui import QColor, QImage, QPainter

from kyrin.actions.telegram_verification import telegram_left_label
from kyrin.actions.visible_control import unique_visible_target
from kyrin.app.qt.screen_text_reader import ReadRegion, ScreenTextReader
from kyrin.vision.ocr.contracts import (
    OcrCapabilities,
    OcrDevice,
    OcrOptions,
    OcrResult,
    RecognizedText,
    TextBox,
)
from kyrin.vision.text_reader import IdentifiedWindowText
from tests.actions import test_desktop_control_helper as control_tests
from tests.actions import test_telegram_portal_focus as telegram_tests
from tests.app.test_qt_screen_access import FakeBus, StubAccess, _reply
from tests.app.test_qt_screen_text_reader import _app, _until
from tests.vision.test_gnome_session_gate import _EXTENSION, _FAKES

control_helper = control_tests.helper
telegram_helper = telegram_tests.helper


class RecordingBus:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple]] = []

    def call_sync(self, _bus, _obj, _iface, method, arguments, *_rest):
        self.calls.append((method, arguments))


def _produce(case: dict[str, object]) -> dict[str, object]:
    gjs = shutil.which("gjs")
    if gjs is None:
        pytest.skip("GJS is not installed")
    source = "\n".join(
        line
        for line in _EXTENSION.read_text().splitlines()
        if not line.startswith("import ")
    ).replace("export default class", "class")
    program = r"""
let frame = {...fixture.frame};
let buffer = {...fixture.buffer};
const actor = {
    get_position: () => [buffer.x, buffer.y],
    get_size: () => [buffer.width, buffer.height],
};
window.get_frame_rect = () => ({...frame});
window.get_buffer_rect = () => ({...buffer});
window.get_compositor_private = () => actor;
global.display.get_monitor_scale = () => fixture.monitorScale;
imageBytes = new Uint8Array(fixture.png);
let area = {...frame}; // GNOME 50 returns frame, even when PNG includes shadows.
Shell.Screenshot.prototype.screenshot_window_finish = () => [true, {...area}];
if (fixture.change === 'actor') actor.get_position = () => [buffer.x + 1, buffer.y];
if (fixture.change === 'during_capture') {
    Shell.Screenshot.prototype.screenshot_window_finish = () => {
        frame.x++; buffer.x++;
        return [true, {...area}];
    };
}
const extension = new KyrinWindowCapturePrototype();
extension.enable();
request(extension, 'RequestSession', ':1.42');
dialogs.at(-1).buttons[1].action();
const captured = request(extension, 'CaptureActiveWindow', ':1.42');
const values = captured.reply.values;
values[values.length - 1] = Array.from(values.at(-1));
let valid = false;
if (values[0]) {
    const id = JSON.parse(values[10]).capture_id;
    if (fixture.change === 'buffer') buffer.x++;
    if (fixture.change === 'monitor') window.get_monitor = () => 2;
    if (fixture.change === 'during_validation') {
        Shell.Screenshot.prototype.screenshot_window_finish = () => {
            buffer.x++;
            return [true, {...area}];
        };
    }
    extension.ValidateCaptureRegionsAsync([id, [fixture.box]], {
        return_value: reply => {valid = reply.values[0];},
    });
}
print(JSON.stringify({values, valid}));
"""
    result = subprocess.run(
        [
            gjs,
            "-c",
            "const fixture = "
            + json.dumps(case)
            + ";\n"
            + _FAKES
            + "\nconst GdkPixbuf = imports.gi.GdkPixbuf;\n"
            + source
            + program,
        ],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def _fixture(scale: float, origin: tuple[int, int], local: tuple[int, int]):
    x, y = origin
    frame = dict(x=x, y=y, width=800, height=600)
    # Asymmetric client-side shadow: left=12, top=20, right=28, bottom=36.
    buffer = dict(x=x - 12, y=y - 20, width=840, height=656)
    size = (round(840 * scale), round(656 * scale))
    box = tuple(
        round(value * scale) for value in (local[0] + 12, local[1] + 20, 16, 16)
    )
    image = QImage(*size, QImage.Format.Format_RGB888)
    image.fill(0x202020)
    painter = QPainter(image)
    painter.fillRect(*box, QColor(255, 0, 0))
    painter.end()
    data = QByteArray()
    stream = QBuffer(data)
    assert stream.open(QIODevice.OpenModeFlag.WriteOnly)
    assert image.save(stream, "PNG")
    return (
        dict(
            frame=frame,
            buffer=buffer,
            monitorScale=1,
            png=list(bytes(data)),
            box=box,
            change="stable",
        ),
        size,
        box,
    )


@pytest.mark.parametrize("scale", [1, 1.25, 1.5, 2])
@pytest.mark.parametrize("origin", [(40, 60), (-1200, -800)])
@pytest.mark.parametrize("movement", ["stable", "before_input", "after_motion"])
@pytest.mark.parametrize(
    ("region", "local"),
    [
        (None, (24, 24)),
        (None, (760, 24)),
        (None, (24, 560)),
        (None, (760, 560)),
        (None, (400, 300)),
        ("chat_header", (600, 40)),
        ("left_chat_list", (100, 160)),
    ],
)
def test_producer_to_crop_resize_and_actuators(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    control_helper: ModuleType,
    telegram_helper: ModuleType,
    scale: float,
    origin: tuple[int, int],
    region: ReadRegion,
    local: tuple[int, int],
    movement: str,
) -> None:
    app = _app(monkeypatch)
    case, size, source_box = _fixture(scale, origin, local)
    produced = _produce(case)
    assert produced["valid"] is True
    values = produced["values"]
    assert values[2:6] == list(case["buffer"].values())
    metadata = json.loads(values[10])
    assert metadata["coordinate_space"] == "logical_desktop"
    assert metadata["image_coordinate_space"] == "source_png_pixels"
    assert metadata["mapping_source"] == "gnome-buffer-actor-v1"
    assert metadata["scale_x"] == metadata["scale_y"] == scale
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    monkeypatch.setattr(
        "kyrin.app.qt.screen_access.QDBusConnection.sessionBus", lambda: FakeBus()
    )
    values[-1] = bytes(values[-1])
    access = StubAccess(
        {
            "RequestPersistentSession": _reply(True),
            "CaptureActiveWindow": _reply(*values),
        }
    )
    access.request_session()
    resize = 2 if region == "left_chat_list" else 1
    offset = int(size[0] * 0.3) if region == "chat_header" else 0
    ocr_box = TextBox(
        (source_box[0] - offset) * resize,
        source_box[1] * resize,
        source_box[2] * resize,
        source_box[3] * resize,
    )

    class MarkerOcr:
        capabilities = OcrCapabilities(frozenset({OcrDevice.CPU}), frozenset({"eng"}))

        def recognize(self, png: bytes, _options: OcrOptions) -> OcrResult:
            actual = QImage.fromData(png)
            assert actual.pixelColor(
                ocr_box.left + ocr_box.width // 2, ocr_box.top + ocr_box.height // 2
            ) == QColor(255, 0, 0)
            expected_width = (
                int(size[0] * 0.36) * 2 if resize == 2 else size[0] - offset
            )
            assert actual.width() == expected_width
            assert actual.height() == (
                int(size[1] * 0.2) if offset else size[1] * resize
            )
            return OcrResult(
                (RecognizedText("Settings", ocr_box, 0.99),),
                "eng",
                OcrDevice.CPU,
                "marker",
            )

    reader = ScreenTextReader(
        access, MarkerOcr(), lambda: ("test.desktop", 123), OcrOptions("eng")
    )
    observations: list[IdentifiedWindowText] = []
    errors: list[str] = []
    reader.completed.connect(observations.append)
    reader.failed.connect(errors.append)
    try:
        assert reader.read(region=region)
        _until(app, lambda: bool(observations or errors))
        assert not errors
        observation = observations[0]
        target = unique_visible_target(observation, "test.desktop", 123, "Settings")
        assert target is not None and target.geometry is not None
        assert (target.left, target.top, target.width, target.height) == source_box
        assert target.geometry.crop_origin == (offset, 0)
        assert target.geometry.ocr_resize == (resize, resize)
        expected = (origin[0] + local[0] + 8, origin[1] + local[1] + 8)
        geometry = target.geometry
        box = (*source_box, *size)
        for helper in (control_helper, telegram_helper):
            bus = RecordingBus()
            frame = ("test.desktop", 123, *case["frame"].values())
            moved = (*frame[:2], frame[2] + 64, *frame[3:])
            frames = iter(
                [
                    (*(moved if movement == "before_input" else frame), 0, 0),
                    (*(moved if movement == "after_motion" else frame), *expected),
                ]
            )
            monkeypatch.setattr(
                helper, "_window_and_pointer", lambda frames=frames: next(frames)
            )
            monkeypatch.setattr(helper, "_focused_window_token", lambda: "7")
            monkeypatch.setattr(helper, "monotonic", lambda: 101.0)
            monkeypatch.setattr(
                helper,
                "_capture_still_current",
                lambda _id, _regions: produced["valid"],
            )
            helper.GLib.Variant = lambda _signature, value: value
            helper.Gio.DBusCallFlags = type("Flags", (), {"NONE": 0})

            if helper is control_helper:
                monkeypatch.setattr(helper, "_wait_for_pointer", lambda *_args: True)
                result = helper._click(
                    bus,
                    "/session",
                    frame[:2],
                    box,
                    "Settings",
                    None,
                    False,
                    None,
                    geometry,
                )
                assert (
                    result
                    == {
                        "stable": "CLICK_DISPATCHED",
                        "before_input": "TARGET_CHANGED:frame_size",
                        "after_motion": "TARGET_CHANGED:pointer_or_window",
                    }[movement]
                )
            elif region == "left_chat_list":
                telegram_target = telegram_left_label(
                    observation, "test.desktop", 123, "Settings", menu=True
                )
                assert (
                    telegram_target is not None and telegram_target.geometry == geometry
                )
                monkeypatch.setattr(helper, "sleep", lambda _seconds: None)
                assert helper._click_verified_box(
                    bus,
                    "/session",
                    frame[:2],
                    box,
                    menu_item=True,
                    geometry=geometry,
                    evidence_regions=(source_box,),
                ) is (movement == "stable")
            else:
                continue
            expected_calls = [
                ("NotifyPointerMotion", ("/session", {}, *map(float, expected))),
                ("NotifyPointerButton", ("/session", {}, helper.LEFT_BUTTON, 1)),
                ("NotifyPointerButton", ("/session", {}, helper.LEFT_BUTTON, 0)),
            ]
            assert bus.calls == (
                expected_calls
                if movement == "stable"
                else expected_calls[:1]
                if movement == "after_motion"
                else []
            )
    finally:
        reader.close()
        access.close()


@pytest.mark.parametrize(
    "change", ["actor", "during_capture", "buffer", "monitor", "during_validation"]
)
def test_producer_rejects_ambiguous_or_changed_image_extent(
    monkeypatch: pytest.MonkeyPatch,
    change: str,
) -> None:
    _app(monkeypatch)
    case, _, _ = _fixture(1.25, (-1200, -800), (100, 160))
    case["change"] = change
    produced = _produce(case)
    if change in {"actor", "during_capture"}:
        assert produced["values"][0] == ""
    else:
        assert produced["values"][0] == "test.desktop"
        assert produced["valid"] is False
