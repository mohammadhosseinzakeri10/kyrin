"""Versioned, content-free failures for the shared accessibility inventory.

Names and structures travel only as internal targeting evidence, never as errors.
A failed or incomplete read is not an empty successful inventory.
"""

import json
from dataclasses import dataclass

from kyrin.desktop.accessibility_target import AccessibilityTarget

SCAN_FAILURES = frozenset(
    {
        "window_identity_unavailable",
        "focus_changed",
        "frame_unavailable",
        "window_ambiguous_or_inactive",
        "window_invalid",
        "window_bounds_unavailable",
        "window_bounds_mismatch",
        "tree_incomplete",
        "ancestry_inconsistent",
        "accessibility_error",
        "helper_error",
        "helper_timeout",
        "helper_unavailable",
        "invalid_reply",
    }
)
TARGET_FAILURES = frozenset(
    {
        "target_not_found",
        "target_ambiguous",
        "target_invalid",
        "ocr_unavailable",
        "ocr_geometry_mismatch",
        "application_not_exported",
        "action_unavailable",
    }
)
REJECTION_REASONS = {
    "incomplete window inventory": "tree_incomplete",
    "no unique active window": "window_ambiguous_or_inactive",
    "invalid active window": "window_invalid",
    "window has no bounds": "window_bounds_unavailable",
    "active window outside focused frame": "window_bounds_mismatch",
    "incomplete accessibility tree": "tree_incomplete",
    "incomplete accessibility children": "tree_incomplete",
    "inconsistent ancestry": "ancestry_inconsistent",
    "observed control disappeared": "target_not_found",
    "ambiguous control": "target_ambiguous",
    "invalid control": "target_invalid",
    "role or ancestry changed": "target_invalid",
    "no unique supported action": "action_unavailable",
}


def _valid_control(item: object) -> bool:
    if not isinstance(item, dict):
        return False
    label, role, checked, x, y, structure = (
        item.get(key) for key in ("label", "role", "checked", "x", "y", "accessibility")
    )
    if (
        not isinstance(label, str)
        or not 1 <= len(label.strip()) <= 80
        or not isinstance(role, str)
        or not role
        or "checked" not in item
        or (checked is not None and type(checked) is not bool)
        or "x" not in item
        or "y" not in item
        or not (
            (x is None and y is None)
            or (type(x) is int and type(y) is int and min(x, y) >= 0)
        )
        or not isinstance(structure, str)
    ):
        return False
    try:
        target = AccessibilityTarget.from_json(structure)
    except ValueError, TypeError:
        return False
    return target.ancestry[-1][1] == role and name_key(
        target.ancestry[-1][2]
    ) == name_key(label)


def name_key(label: str) -> str:
    return " ".join(label.casefold().split())


class ControlObservationError(RuntimeError):
    def __init__(self, reason: str) -> None:
        self.reason = (
            reason if reason in SCAN_FAILURES | TARGET_FAILURES else "invalid_reply"
        )
        super().__init__(self.reason)


@dataclass(frozen=True, slots=True)
class ControlInventoryReply:
    status: str
    controls: tuple[dict[str, object], ...] = ()
    rejected: tuple[tuple[str, str], ...] = ()

    @property
    def complete(self) -> bool:
        return self.status in {"ok", "application_not_exported"}

    def rejection_for(self, label: str) -> str | None:
        return next(
            (
                reason
                for name, reason in self.rejected
                if name_key(name) == name_key(label)
            ),
            None,
        )

    def to_json(self) -> str:
        return json.dumps(
            {
                "version": 1,
                "status": self.status,
                "controls": self.controls,
                "rejected": self.rejected,
            }
        )

    @classmethod
    def from_output(cls, stdout: str, returncode: int) -> ControlInventoryReply:
        if returncode != 0:
            return cls("helper_error")
        try:
            payload = json.loads(stdout)
        except ValueError:
            return cls("invalid_reply")
        if (
            not isinstance(payload, dict)
            or type(payload.get("version")) is not int
            or payload["version"] != 1
        ):
            return cls("invalid_reply")
        status, controls, rejected = (
            payload.get(key) for key in ("status", "controls", "rejected")
        )
        if (
            not isinstance(status, str)
            or status not in SCAN_FAILURES | {"ok", "application_not_exported"}
            or not isinstance(controls, list)
            or len(controls) > 3000
            or not isinstance(rejected, list)
            or len(rejected) > 3000
            or (status != "ok" and (controls or rejected))
            or not all(_valid_control(item) for item in controls)
            or not all(
                isinstance(item, list)
                and len(item) == 2
                and isinstance(item[0], str)
                and 1 <= len(item[0].strip()) <= 80
                and item[1] in ("target_ambiguous", "target_invalid")
                for item in rejected
            )
        ):
            return cls("invalid_reply")
        return cls(
            status,
            tuple(dict(item) for item in controls),
            tuple((name, reason) for name, reason in rejected),
        )
