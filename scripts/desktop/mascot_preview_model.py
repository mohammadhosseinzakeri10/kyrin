"""Offline pose data for the isolated mascot prototype; no desktop actions."""

import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ASSETS = PROJECT_ROOT / "assets/mascot/run-cycle-v2"
SVG_NS = "http://www.w3.org/2000/svg"
ET.register_namespace("", SVG_NS)
Point = tuple[float, float]
Point3 = tuple[float, float, float]
Matrix = tuple[float, float, float, float, float, float]
_POSE_FIELDS = (
    "root_y",
    "left_thigh",
    "left_knee",
    "left_foot",
    "right_thigh",
    "right_knee",
    "right_foot",
    "left_shoulder",
    "left_elbow",
    "right_shoulder",
    "right_elbow",
)


def multiply(first: Matrix, second: Matrix) -> Matrix:
    a, b, c, d, x, y = first
    e, f, g, h, u, v = second
    return (
        a * e + c * f,
        b * e + d * f,
        a * g + c * h,
        b * g + d * h,
        a * u + c * v + x,
        b * u + d * v + y,
    )


def inverse(matrix: Matrix) -> Matrix:
    a, b, c, d, x, y = matrix
    determinant = a * d - b * c
    if abs(determinant) < 0.000001:
        raise ValueError("Degenerate projected limb")
    return (
        d / determinant,
        -b / determinant,
        -c / determinant,
        a / determinant,
        (c * y - d * x) / determinant,
        (b * x - a * y) / determinant,
    )


def segment(start: Point, end: Point, length: float, width_scale: float) -> Matrix:
    dx, dy = end[0] - start[0], end[1] - start[1]
    projected_length = math.hypot(dx, dy)
    if projected_length < 0.000001:
        raise ValueError("Degenerate projected limb")
    return (
        dy / projected_length * width_scale,
        -dx / projected_length * width_scale,
        dx / length,
        dy / length,
        start[0],
        start[1],
    )


def matrix_text(matrix: Matrix) -> str:
    return "matrix(" + " ".join(f"{value:.7f}" for value in matrix) + ")"


@dataclass(frozen=True)
class RunCycle:
    """Frontal pose projection with fixed anatomical lengths, not a 3D renderer."""

    data: dict[str, Any]
    rig: bytes

    @classmethod
    def load(cls) -> RunCycle:
        data = json.loads((ASSETS / "run-cycle.json").read_text())
        if (
            data["schema_version"] != 2
            or data["view"] != "front"
            or len(data["keyframes"]) != 6
        ):
            raise ValueError("Expected frontal version 2 with six running keyframes")
        for frame in data["keyframes"]:
            if any(not math.isfinite(frame[field]) for field in _POSE_FIELDS):
                raise ValueError("Non-finite joint pose")
        return cls(data, (ASSETS / "rig.svg").read_bytes())

    @property
    def duration_ms(self) -> int:
        return int(self.data["duration_ms"])

    def sample(self, phase: float) -> dict[str, float]:
        """Periodic Hermite interpolation avoids a stop at each key pose."""
        frames = self.data["keyframes"]
        position = (phase % 1.0) * len(frames)
        index = math.floor(position)
        t = position - index
        result: dict[str, float] = {}
        for field in _POSE_FIELDS:
            previous, start, end, following = (
                float(frames[i % len(frames)][field])
                for i in (index - 1, index, index + 1, index + 2)
            )
            first_tangent = (end - previous) / 2
            last_tangent = (following - start) / 2
            result[field] = (
                (2 * t**3 - 3 * t**2 + 1) * start
                + (t**3 - 2 * t**2 + t) * first_tangent
                + (-2 * t**3 + 3 * t**2) * end
                + (t**3 - t**2) * last_tangent
            )
        # Bound the entire shoe (including its stroke), rather than only the
        # ankle. The correction translates the whole character, preserving
        # its hip/shoulder attachments; it never stretches a limb.
        lowest = max(self.shoe_floor(result, side) for side in ("left", "right"))
        result["root_y"] = min(result["root_y"], float(self.data["ground_y"]) - lowest)
        return result

    def perspective_scale(self, depth: float) -> float:
        distance = float(self.data["projection_distance"])
        return distance / (distance - depth)

    def project(self, point: Point3) -> Point:
        x, y, depth = point
        scale = self.perspective_scale(depth)
        return (
            48 + (x - 48) * scale,
            self.data["hip_y"]
            + (y - self.data["hip_y"]) * scale
            + depth * self.data["projection_y_depth"],
        )

    def limb_joints(
        self,
        anchor: Point3,
        upper: float,
        lower: float,
        swing: float,
        flex: float,
    ) -> tuple[Point3, Point3, Point3]:
        # Swing and flex act in the depth/vertical plane. They never produce
        # the sideways stride that conflicted with the front-facing head.
        def extend(start: Point3, length: float, angle: float) -> Point3:
            radians = math.radians(angle)
            return (
                start[0],
                start[1] + length * math.cos(radians),
                start[2] - length * math.sin(radians),
            )

        joint = extend(anchor, upper, swing)
        tip = extend(joint, lower, swing + flex)
        return anchor, joint, tip

    def leg_joints(self, pose: dict[str, float], side: str) -> tuple[Point3, ...]:
        return self.limb_joints(
            (self.data["hip_x"][side], self.data["hip_y"], 0),
            self.data["thigh_length"],
            self.data["shin_length"],
            pose[f"{side}_thigh"],
            pose[f"{side}_knee"],
        )

    def shoe_floor(self, pose: dict[str, float], side: str) -> float:
        ankle = self.leg_joints(pose, side)[-1]
        # Frontal shoes stay centered on the ankle and have no right-pointing
        # toe. Include the curved sole's maximum and its 0.9-unit half-stroke.
        return self.project(ankle)[1] + 5.4 * self.perspective_scale(ankle[2])

    def svg(self, phase: float) -> bytes:
        pose = self.sample(phase)
        root = ET.fromstring(self.rig)
        nodes = {node.get("id"): node for node in root.iter() if node.get("id")}
        nodes["character"].set("transform", f"translate(0 {pose['root_y']:.5f})")
        # Head and torso share a frontal plane. Both arms remain beside them.
        nodes["upper-body"].set("transform", "translate(0 0)")
        nodes["head"].set("transform", "translate(0 0)")
        for side in ("left", "right"):
            hip, knee, ankle = self.leg_joints(pose, side)
            thigh = segment(
                self.project(hip),
                self.project(knee),
                self.data["thigh_length"],
                self.perspective_scale(knee[2] / 2),
            )
            shin = segment(
                self.project(knee),
                self.project(ankle),
                self.data["shin_length"],
                self.perspective_scale((knee[2] + ankle[2]) / 2),
            )
            x, y = self.project(ankle)
            scale = self.perspective_scale(ankle[2])
            foot: Matrix = (scale, 0, 0, scale, x, y)
            nodes[f"{side}-thigh"].set("transform", matrix_text(thigh))
            nodes[f"{side}-shin"].set(
                "transform", matrix_text(multiply(inverse(thigh), shin))
            )
            nodes[f"{side}-foot"].set(
                "transform", matrix_text(multiply(inverse(shin), foot))
            )
            knee_x, knee_y = self.project(knee)
            knee_scale = self.perspective_scale(knee[2])
            knee_cap: Matrix = (knee_scale, 0, 0, knee_scale, knee_x, knee_y)
            nodes[f"{side}-knee-cap"].set(
                "transform", matrix_text(multiply(inverse(shin), knee_cap))
            )
            shoulder, elbow, wrist = self.limb_joints(
                (self.data["shoulder_x"][side], 62, 0),
                self.data["upper_arm_length"],
                self.data["forearm_length"],
                pose[f"{side}_shoulder"],
                pose[f"{side}_elbow"],
            )
            arm = segment(
                self.project(shoulder),
                self.project(elbow),
                self.data["upper_arm_length"],
                self.perspective_scale(elbow[2] / 2),
            )
            forearm = segment(
                self.project(elbow),
                self.project(wrist),
                self.data["forearm_length"],
                self.perspective_scale((elbow[2] + wrist[2]) / 2),
            )
            nodes[f"{side}-upper-arm"].set("transform", matrix_text(arm))
            nodes[f"{side}-forearm"].set(
                "transform", matrix_text(multiply(inverse(arm), forearm))
            )
            # A spherical fist or joint does not flatten into a stripe when
            # its connecting limb points toward the viewer.
            for name, point in (("elbow-cap", elbow), ("hand", wrist)):
                x, y = self.project(point)
                scale = self.perspective_scale(point[2])
                sphere: Matrix = (scale, 0, 0, scale, x, y)
                nodes[f"{side}-{name}"].set(
                    "transform", matrix_text(multiply(inverse(forearm), sphere))
                )
        return bytes(ET.tostring(root, encoding="utf-8"))


class Baseline:
    """Replay the actual current execution poses and layered SVG assets."""

    def __init__(self) -> None:
        self.data: dict[str, Any] = json.loads((ASSETS / "baseline.json").read_text())
        self.directory = PROJECT_ROOT / self.data["source_directory"]
        self.verify_source()
        self.layers = {
            name: (
                self.directory / f"mascot{name[0].upper()}{name[1:]}.svg"
            ).read_bytes()
            for name in self.data["pivots"]
        }

    def verify_source(self) -> None:
        for name, expected in self.data["sha256"].items():
            actual = hashlib.sha256((self.directory / name).read_bytes()).hexdigest()
            if actual != expected:
                raise ValueError(
                    f"Baseline source changed; review its snapshot: {name}"
                )

    def svg(self, milliseconds: float) -> bytes:
        frames = self.data["executing"]["frames"]
        neutral = self.data["neutral"]
        total = sum(frame["duration"] for frame in frames)
        current = max(0.0, milliseconds)
        previous = {name: dict(neutral) for name in self.layers}
        if current >= total:
            current %= total
            previous = {
                name: neutral | frames[-1].get(name, {}) for name in self.layers
            }
        pose = previous
        for frame in frames:
            target = {name: neutral | frame.get(name, {}) for name in self.layers}
            if current <= frame["duration"]:
                amount = (1 - math.cos(math.pi * current / frame["duration"])) / 2
                pose = {
                    name: {
                        key: previous[name][key]
                        + (value - previous[name][key]) * amount
                        for key, value in target[name].items()
                    }
                    for name in self.layers
                }
                break
            current -= frame["duration"]
            previous = target
        root = ET.Element(
            f"{{{SVG_NS}}}svg",
            {
                "width": "112",
                "height": "112",
                "viewBox": "0 0 112 112",
            },
        )

        def actor(name: str, parent: ET.Element) -> ET.Element:
            value = pose[name]
            x, y = (number * 112 for number in self.data["pivots"][name])
            return ET.SubElement(
                parent,
                f"{{{SVG_NS}}}g",
                {
                    "transform": (
                        f"translate({value['translation_x']} {value['translation_y']}) "
                        f"translate({x} {y}) rotate({value['rotation_angle_z']}) "
                        f"scale({value['scale_x']} {value['scale_y']}) "
                        f"translate({-x} {-y})"
                    )
                },
            )

        def image(name: str, parent: ET.Element) -> None:
            layer = ET.fromstring(self.layers[name])
            # Layer-local gradient IDs must remain distinct in a combined SVG.
            for node in layer.iter():
                for attribute, value in list(node.attrib.items()):
                    if attribute == "id":
                        node.set(attribute, f"{name}-{value}")
                    elif "url(#" in value:
                        node.set(attribute, value.replace("url(#", f"url(#{name}-"))
            # Qt SVG Tiny rejects nested SVG viewports. Express the original
            # 96x120 image's centered fit inside 112x112 as an explicit group.
            fitted = ET.SubElement(
                parent,
                f"{{{SVG_NS}}}g",
                {
                    "transform": "translate(11.2 0) scale(0.9333333333333333)",
                },
            )
            fitted.extend(layer)

        for name in ("leftLeg", "rightLeg", "leftArm", "rightArm", "body"):
            image(name, actor(name, root))
        head = actor("head", root)
        image("head", head)
        image("eyes", actor("eyes", head))
        return bytes(ET.tostring(root, encoding="utf-8"))
