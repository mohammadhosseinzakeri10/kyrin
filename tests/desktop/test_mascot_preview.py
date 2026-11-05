"""Validate the isolated run rig, loop seam and exported comparison rendering."""

import math
from xml.etree import ElementTree as ET

import pytest

from scripts.desktop.mascot_preview_model import Baseline, RunCycle


def test_run_cycle_seam_has_continuous_pose_and_velocity() -> None:
    cycle = RunCycle.load()
    epsilon = 0.000001
    start = cycle.sample(0)
    assert cycle.sample(1) == start
    before, after = cycle.sample(-epsilon), cycle.sample(epsilon)
    for name, value in start.items():
        assert before[name] == pytest.approx(after[name], abs=0.002)
        incoming = (value - before[name]) / epsilon
        outgoing = (after[name] - value) / epsilon
        assert incoming == pytest.approx(outgoing, abs=0.02)


def test_knees_and_ankles_preserve_lengths_throughout_the_cycle() -> None:
    cycle = RunCycle.load()
    for index in range(240):
        pose = cycle.sample(index / 240)
        for side in ("left", "right"):
            hip, knee, ankle = cycle.leg_joints(pose, side)
            assert math.dist(hip, knee) == pytest.approx(cycle.data["thigh_length"])
            assert math.dist(knee, ankle) == pytest.approx(cycle.data["shin_length"])
            assert 0 < pose[f"{side}_knee"] < 125
            assert cycle.shoe_floor(pose, side) + pose["root_y"] <= 115.000001


def test_cycle_alternates_ground_contact_and_has_a_flight_phase() -> None:
    cycle = RunCycle.load()
    for phase, planted in ((0, "left"), (0.5, "right")):
        pose = cycle.sample(phase)
        other = "right" if planted == "left" else "left"
        assert cycle.shoe_floor(pose, planted) + pose["root_y"] == pytest.approx(115)
        assert cycle.shoe_floor(pose, other) + pose["root_y"] < 105
        assert pose[f"{planted}_thigh"] < 0
        assert pose[f"{other}_shoulder"] < 0
    flight = cycle.sample(2 / 6)
    assert all(
        cycle.shoe_floor(flight, side) + flight["root_y"] < 113
        for side in ("left", "right")
    )
    roots = [cycle.sample(index / 240)["root_y"] for index in range(240)]
    assert max(roots) - min(roots) < 4


def test_nested_rig_keeps_attachments_and_front_arm_visible_in_layer_order() -> None:
    root = ET.fromstring(RunCycle.load().svg(0.25))
    nodes = {node.get("id"): node for node in root.iter()}
    parents = {child.get("id"): parent for parent in root.iter() for child in parent}
    assert parents["upper-body"] is nodes["character"]
    for side in ("left", "right"):
        assert parents[f"{side}-thigh"] is nodes["character"]
        assert parents[f"{side}-shin"] is nodes[f"{side}-thigh"]
        assert parents[f"{side}-foot"] is nodes[f"{side}-shin"]
        assert parents[f"{side}-forearm"] is nodes[f"{side}-upper-arm"]
        assert parents[f"{side}-upper-arm"] is nodes["upper-body"]
    order = [node.get("id") for node in nodes["upper-body"]]
    assert order.index("left-upper-arm") > order.index("body")
    assert order.index("right-upper-arm") > order.index("body")
    assert parents["head"] is nodes["upper-body"]
    assert parents["eyes"] is nodes["head"]


def test_front_view_steps_in_depth_and_remains_symmetric_about_the_body() -> None:
    cycle = RunCycle.load()
    for index in range(240):
        pose = cycle.sample(index / 240)
        opposite = cycle.sample(index / 240 + 0.5)
        left = cycle.leg_joints(pose, "left")
        mirrored_right = cycle.leg_joints(opposite, "right")
        for first, second in zip(left, mirrored_right, strict=True):
            assert first[0] == 40
            assert second[0] == 56
            assert first[1:] == pytest.approx(second[1:])
            screen_left, screen_right = cycle.project(first), cycle.project(second)
            assert screen_left[0] + screen_right[0] == pytest.approx(96)
            assert abs(screen_left[0] - 40) < 2
            assert screen_left[0] < 48 < screen_right[0]
    nodes = {node.get("id"): node for node in ET.fromstring(cycle.svg(0)).iter()}
    assert nodes["upper-body"].get("transform") == "translate(0 0)"
    assert nodes["head"].get("transform") == "translate(0 0)"


def test_fists_do_not_flatten_when_forearms_are_foreshortened() -> None:
    from scripts.desktop.mascot_preview_model import Matrix, multiply

    def matrix(node: ET.Element) -> Matrix:
        text = node.attrib["transform"]
        values = [float(value) for value in text[7:-1].split()]
        assert len(values) == 6
        return values[0], values[1], values[2], values[3], values[4], values[5]

    cycle = RunCycle.load()
    for index in range(120):
        nodes = {
            node.get("id"): node
            for node in ET.fromstring(cycle.svg(index / 120)).iter()
        }
        for side in ("left", "right"):
            arm = matrix(nodes[f"{side}-upper-arm"])
            forearm = matrix(nodes[f"{side}-forearm"])
            hand = matrix(nodes[f"{side}-hand"])
            a, b, c, d, _, _ = multiply(multiply(arm, forearm), hand)
            assert a == pytest.approx(d, abs=0.00001)
            assert b == pytest.approx(0, abs=0.00001)
            assert c == pytest.approx(0, abs=0.00001)
            assert a > 0.8


@pytest.fixture
def qt_app(monkeypatch: pytest.MonkeyPatch) -> object:
    pytest.importorskip("PySide6")
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance()
    if not isinstance(app, QApplication):
        app = QApplication([])
    return app


def test_both_characters_render_without_clipping_at_real_and_double_size(
    qt_app: object,
) -> None:
    del qt_app
    from PySide6.QtGui import QImage

    from scripts.desktop.preview_mascot import render_svg

    cycle, baseline = RunCycle.load(), Baseline()
    for pixels in (112, 224):
        for index in range(120):
            for source in (cycle.svg(index / 120), baseline.svg(1920 + index * 16)):
                image = render_svg(source, pixels)
                rgba = image.convertToFormat(QImage.Format.Format_RGBA8888)
                raw = bytes(rgba.constBits())
                alpha = raw[3::4]
                assert sum(value > 0 for value in alpha) > pixels * pixels * 0.2
                assert not any(alpha[:pixels] + alpha[-pixels:])
                assert not any(alpha[::pixels] + alpha[pixels - 1 :: pixels])


def test_preview_starts_still_and_scrubbing_and_cadence_keep_phase(
    qt_app: object,
) -> None:
    del qt_app
    from scripts.desktop.preview_mascot import Preview

    preview = Preview()
    try:
        assert not preview.timer.isActive()
        preview.slider.setValue(250)
        assert preview.canvas.milliseconds / preview.canvas.duration == 0.25
        preview.cadence.setCurrentIndex(2)
        assert preview.canvas.duration == 720
        assert preview.canvas.milliseconds / preview.canvas.duration == 0.25
        preview.play.click()
        assert preview.timer.isActive()
        preview.pause.click()
        assert not preview.timer.isActive()
    finally:
        preview.close()
    assert not preview.timer.isActive()


def test_preview_playback_is_bounded_to_six_cycles(
    qt_app: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del qt_app
    from scripts.desktop import preview_mascot

    preview = preview_mascot.Preview()
    try:
        monkeypatch.setattr(
            "scripts.desktop.preview_mascot.time.monotonic", lambda: 10.0
        )
        preview.play.click()
        monkeypatch.setattr(
            "scripts.desktop.preview_mascot.time.monotonic", lambda: 15.0
        )
        preview._tick()
        assert not preview.timer.isActive()
        assert preview.canvas.milliseconds == preview.canvas.duration * 6
    finally:
        preview.close()
