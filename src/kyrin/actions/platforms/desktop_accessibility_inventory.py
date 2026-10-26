"""Read names of actionable controls in the currently focused window.

This small process uses Ubuntu's system Python for AT-SPI. It never clicks.
"""

import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

import gi  # type: ignore[import-not-found]

gi.require_version("Atspi", "2.0")
from gi.repository import Atspi, GLib  # type: ignore[import-not-found]  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from kyrin.actions.platforms.control_inventory_protocol import (  # noqa: E402
    REJECTION_REASONS,
    ControlInventoryReply,
)
from kyrin.actions.platforms.desktop_accessibility import (  # noqa: E402
    ControlUnavailable,
    control_snapshot,
)
from kyrin.actions.platforms.desktop_accessibility_transport_probe import (  # noqa: E402
    probe_missing_child,
)
from kyrin.actions.platforms.telegram_portal_helper import (  # noqa: E402
    _focused_identity,
    _focused_window_token,
    _window_and_pointer,
)


def observe_controls(app_id: str, pid: int, window_token: str) -> ControlInventoryReply:
    identity = _focused_identity()
    token = _focused_window_token()
    if identity is None or token is None:
        return ControlInventoryReply("window_identity_unavailable")
    if identity != (app_id, pid) or not window_token or token != window_token:
        return ControlInventoryReply("focus_changed")
    frame = _window_and_pointer()
    if frame is None:
        return ControlInventoryReply("frame_unavailable")
    if frame[:2] != (app_id, pid):
        return ControlInventoryReply("focus_changed")
    _, _, frame_x, frame_y, frame_w, frame_h, *_ = frame
    try:
        desktop = Atspi.get_desktop(0)
        exported = any(
            desktop.get_child_at_index(i).get_process_id() == pid
            for i in range(desktop.get_child_count())
        )
        snapshot = control_snapshot(
            desktop, pid, Atspi, (frame_x, frame_y, frame_w, frame_h)
        )
    except ControlUnavailable as error:
        return ControlInventoryReply(
            REJECTION_REASONS.get(str(error), "accessibility_error")
        )
    except GLib.Error, TypeError, ValueError, AttributeError:
        return ControlInventoryReply("accessibility_error")
    names = [" ".join(item[0].get_name().casefold().split()) for item in snapshot]
    counts = Counter(names)
    controls: list[dict[str, object]] = []
    rejected: dict[str, str] = {}
    for (node, target, valid, checked, point), name in zip(
        snapshot, names, strict=True
    ):
        # Keep rejection evidence so another reader cannot revive this target.
        if counts[name] != 1:
            rejected[node.get_name().strip()] = "target_ambiguous"
            continue
        if not valid:
            rejected[node.get_name().strip()] = "target_invalid"
            continue
        controls.append(
            {
                "label": node.get_name().strip(),
                "role": str(node.get_role()),
                "checked": checked,
                "x": point[0] - frame_x if point is not None else None,
                "y": point[1] - frame_y if point is not None else None,
                "accessibility": target.to_json(),
            }
        )
    if (
        _focused_identity() != (app_id, pid)
        or not window_token
        or _focused_window_token() != window_token
    ):
        return ControlInventoryReply("focus_changed")
    return ControlInventoryReply(
        "ok" if exported else "application_not_exported",
        tuple(controls),
        tuple(rejected.items()),
    )


def list_controls(app_id: str, pid: int, window_token: str) -> list[dict[str, object]]:
    """Compatibility view for callers that only need usable controls."""
    return list(observe_controls(app_id, pid, window_token).controls)


def _diagnose_actions(node: Any) -> dict[str, object]:
    """Only fixed action vocabulary for explicitly requested diagnostic labels."""
    known = {"click", "press", "activate", "open", "jump", "toggle", "check", "uncheck"}
    try:
        action = node.get_action_iface()
        if action is None:
            return {"status": "absent"}
        count = action.get_n_actions()
        if type(count) is not int or not 0 <= count <= 64:
            return {"status": "invalid"}
        names = [action.get_action_name(index).casefold() for index in range(count)]
    except GLib.Error, TypeError, ValueError, AttributeError, RuntimeError:
        return {"status": "unavailable"}
    recognized = [
        {"name": name, "index": index}
        for index, name in enumerate(names)
        if name in known
    ]
    return {
        "status": "ok",
        "count": count,
        "known": recognized,
        "other_count": count - len(recognized),
    }


def diagnose_controls(
    labels: list[str], *, include_geometry: bool = False
) -> dict[str, object]:
    """Opt-in report, disclosing only labels explicitly supplied by the owner.

    Does not invoke actions, acquire input, capture screens or dump tree names.
    Partial/changed snapshots are diagnostic evidence only, never authorization.
    """
    metrics: dict[str, int] = {"matching_applications": 0}
    report: dict[str, object] = {"status": "unavailable", "scan": metrics}
    geometry: dict[str, object] | None = {} if include_geometry else None
    if geometry is not None:
        report["geometry"] = geometry
    identity = _focused_identity()
    token = _focused_window_token()
    if identity is None or not token:
        return {**report, "status": "window_identity_unavailable"}
    frame = _window_and_pointer()
    if frame is None or frame[:2] != identity:
        return {**report, "status": "focus_changed"}
    try:
        snapshot = control_snapshot(
            Atspi.get_desktop(0),
            identity[1],
            Atspi,
            frame[2:6],
            diagnostics=metrics,
            geometry=geometry,
            child_probe=probe_missing_child,
        )
    except ControlUnavailable as error:
        if _focused_identity() != identity or _focused_window_token() != token:
            return {**report, "status": "focus_changed"}
        # These reasons are fixed strings from the resolver, never page content.
        return {
            **report,
            "status": "scan_rejected",
            "reason": str(error),
            "reason_code": REJECTION_REASONS.get(str(error), "accessibility_error"),
        }
    except GLib.Error, TypeError, ValueError, AttributeError, RuntimeError:
        if "ancestry_child_missing" in metrics:
            metrics["ancestry_probe_failed"] = 1
            return {
                **report,
                "status": "scan_rejected",
                "reason": "inconsistent ancestry",
                "reason_code": "ancestry_inconsistent",
            }
        return {**report, "status": "accessibility_error"}
    if _focused_identity() != identity or _focused_window_token() != token:
        return {**report, "status": "focus_changed"}
    metrics["named_controls"] = len(snapshot)
    metrics["valid_controls"] = sum(item[2] for item in snapshot)
    matches: list[dict[str, object]] = []
    for label in labels:
        normalized = " ".join(label.casefold().split())
        candidates = [
            item
            for item in snapshot
            if " ".join(item[0].get_name().casefold().split()) == normalized
        ]
        matches.append(
            {
                "requested_label": label,
                "matches": len(candidates),
                "controls": [
                    {
                        "role": str(node.get_role()),
                        "valid": valid,
                        "checked": checked,
                        "has_coordinates": point is not None,
                        "has_structural_identity": bool(target.ancestry),
                        "depth": len(target.ancestry),
                        "actions": _diagnose_actions(node),
                    }
                    for node, target, valid, checked, point in candidates
                ],
            }
        )
    if _focused_identity() != identity or _focused_window_token() != token:
        return {**report, "status": "focus_changed"}
    return {
        **report,
        "status": "ok"
        if metrics["matching_applications"]
        else "application_not_exported",
        "requested": matches,
    }


if __name__ == "__main__":
    try:
        if len(sys.argv) == 3 and sys.argv[1] in {
            "--diagnose-current",
            "--diagnose-current-geometry",
        }:
            labels = json.loads(sys.argv[2])
            if (
                not isinstance(labels, list)
                or len(labels) > 20
                or not all(
                    isinstance(label, str) and 1 <= len(label.strip()) <= 80
                    for label in labels
                )
            ):
                raise ValueError("invalid diagnostic labels")
            print(
                json.dumps(
                    diagnose_controls(
                        labels,
                        include_geometry=sys.argv[1] == "--diagnose-current-geometry",
                    ),
                    ensure_ascii=False,
                )
            )
            sys.exit(0)
        if len(sys.argv) != 4:
            raise ValueError("expected app id, process id and window token")
        print(observe_controls(sys.argv[1], int(sys.argv[2]), sys.argv[3]).to_json())
    except GLib.Error, RuntimeError, ValueError, OSError, AttributeError:
        print(ControlInventoryReply("accessibility_error").to_json())
