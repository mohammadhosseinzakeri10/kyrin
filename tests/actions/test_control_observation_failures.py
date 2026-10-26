"""Shared observation failures stay distinguishable and cannot authorize input."""

import json
import subprocess
from time import monotonic

import pytest

from kyrin.actions.models import ActionKey, ActionOutcome, ActionRequest, ActionResult
from kyrin.actions.platforms import desktop_control
from kyrin.actions.platforms.control_inventory_protocol import ControlInventoryReply
from kyrin.commands.models import CommandIntent, CommandKind
from kyrin.desktop.window_observation import WindowObservation


class Delegate:
    def execute(self, request: ActionRequest) -> ActionResult:
        pytest.fail("control must not delegate")


class NoFallback:
    def ready(self) -> bool:
        pytest.fail("failed or rejected observation must not permit OCR fallback")

    def find_visible_control(self, *_args: object) -> None:
        pytest.fail("failed observation must not capture")


@pytest.mark.parametrize(
    "app", ["browser.desktop", "editor.desktop", "settings.desktop"]
)
@pytest.mark.parametrize(
    "status",
    ["helper_error", "tree_incomplete", "window_bounds_mismatch", "focus_changed"],
)
def test_common_scan_failure_reaches_action_result(
    monkeypatch: pytest.MonkeyPatch,
    app: str,
    status: str,
) -> None:
    def run(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        assert args[1].endswith("desktop_accessibility_inventory.py")
        return subprocess.CompletedProcess(
            args,
            1 if status == "helper_error" else 0,
            json.dumps(
                {"version": 1, "status": status, "controls": [], "rejected": []}
            ),
            "private exception data",
        )

    monkeypatch.setattr(desktop_control, "run_process", run)
    now = monotonic()
    request = ActionRequest(
        ActionKey(0, 1),
        CommandIntent(
            CommandKind.VISIBLE_CONTROL,
            "Test Button",
            control_window_app=app,
            control_observation=WindowObservation(
                app, 42, "window-7", "initial", now, now + 10
            ),
        ),
    )
    executor = desktop_control.DesktopControlExecutor(
        Delegate(),
        identity_reader=lambda: (app, 42),
        token_reader=lambda: "window-7",
        confirmation=lambda _prompt: True,
        verifier=NoFallback(),
    )
    result = executor.execute(request)
    assert result.outcome is ActionOutcome.FAILED
    assert result.error_code == "visible_control_observation:" + status


@pytest.mark.parametrize(
    "payload",
    [
        [],
        {"version": True, "status": "ok", "controls": [], "rejected": []},
        {"version": 2, "status": "ok", "controls": [], "rejected": []},
        {"version": 1, "status": "private data", "controls": [], "rejected": []},
        {"version": 1, "status": "ok", "controls": [{"label": "Test"}], "rejected": []},
        {
            "version": 1,
            "status": "ok",
            "controls": [],
            "rejected": [["Test", "private data"]],
        },
        {
            "version": 1,
            "status": "tree_incomplete",
            "controls": [],
            "rejected": [["Test", "target_invalid"]],
        },
    ],
)
def test_unversioned_malformed_or_partial_inventory_cannot_become_empty_success(
    payload: object,
) -> None:
    reply = ControlInventoryReply.from_output(json.dumps(payload), 0)
    assert not reply.complete and reply.status == "invalid_reply"
    assert reply.controls == () and reply.rejected == ()


@pytest.mark.parametrize("reason", ["target_ambiguous", "target_invalid"])
def test_rejected_control_cannot_reach_ocr_or_input(
    monkeypatch: pytest.MonkeyPatch,
    reason: str,
) -> None:
    reply = ControlInventoryReply("ok", rejected=(("Test Button", reason),))
    monkeypatch.setattr(
        desktop_control,
        "run_process",
        lambda args, **_kwargs: subprocess.CompletedProcess(
            args, 0, reply.to_json(), ""
        ),
    )
    now = monotonic()
    request = ActionRequest(
        ActionKey(0, 1),
        CommandIntent(
            CommandKind.VISIBLE_CONTROL,
            "Test Button",
            control_observation=WindowObservation(
                "example.desktop", 42, "window-7", "initial", now, now + 10
            ),
        ),
    )
    executor = desktop_control.DesktopControlExecutor(
        Delegate(),
        identity_reader=lambda: ("example.desktop", 42),
        token_reader=lambda: "window-7",
        confirmation=lambda _prompt: pytest.fail(
            "rejected target must not be confirmed"
        ),
        verifier=NoFallback(),
    )
    assert (
        executor.execute(request).error_code == "visible_control_observation:" + reason
    )
