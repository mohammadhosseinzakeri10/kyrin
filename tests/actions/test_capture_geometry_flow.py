"""Generic and Telegram targets retain the capture's same geometry."""

import json
import subprocess
from time import monotonic

import pytest

from kyrin.actions.models import ActionKey, ActionOutcome, ActionRequest, ActionResult
from kyrin.actions.platforms import desktop_control
from kyrin.actions.platforms.telegram import (
    TelegramSavedMessagesExecutor,
    _same_search_box,
)
from kyrin.actions.telegram_verification import ChatSearchMatch, telegram_left_label
from kyrin.actions.visible_control import VisibleControlTarget, unique_visible_target
from kyrin.commands.models import CommandIntent, CommandKind
from kyrin.desktop.window_observation import WindowObservation
from kyrin.vision.capture_geometry import CaptureGeometry
from kyrin.vision.ocr.contracts import OcrDevice, OcrResult, RecognizedText, TextBox
from kyrin.vision.text_reader import IdentifiedWindowText
from tests.actions.chat_verifier_stub import StubChatVerifier


def test_both_target_paths_keep_one_capture_geometry() -> None:
    geometry = CaptureGeometry(
        "logical_desktop",
        0,
        (10, 20, 800, 600),
        (1000, 750),
        1.25,
        1.25,
        (0, 0, 0, 0),
        (0, 0),
        (1, 1),
        "window-7",
        "capture-1",
        100.0,
        (10, 20, 800, 600),
    )
    observation = IdentifiedWindowText(
        "org.telegram.desktop",
        42,
        OcrResult(
            (RecognizedText("Settings", TextBox(50, 100, 100, 20), 0.95),),
            "eng",
            OcrDevice.CPU,
            "test",
        ),
        (1000, 750),
        geometry=geometry,
    )
    generic = unique_visible_target(observation, "org.telegram.desktop", 42, "Settings")
    telegram = telegram_left_label(
        observation, "org.telegram.desktop", 42, "Settings", menu=True
    )
    assert generic is not None and generic.geometry is geometry
    assert telegram is not None and telegram.geometry is geometry


def test_both_executors_send_the_same_geometry_to_their_click_helpers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    geometry = CaptureGeometry(
        "logical_desktop",
        0,
        (10, 20, 800, 600),
        (1000, 750),
        1.25,
        1.25,
        (0, 0, 0, 0),
        (0, 0),
        (1, 1),
        "window-7",
        "capture-1",
        100.0,
        (10, 20, 800, 600),
    )
    sent: list[list[str]] = []

    def run(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        if len(args) > 2 and args[2] == "semantic":
            return subprocess.CompletedProcess(args, 0, "NO_ACCESSIBLE_ACTION", "")
        sent.append(args)
        marker = "CLICK_DISPATCHED" if len(sent) == 1 else "CHAT_RESULT_CLICKED"
        return subprocess.CompletedProcess(args, 0, marker, "")

    monkeypatch.setattr("kyrin.actions.platforms.desktop_control.run_process", run)
    monkeypatch.setattr("kyrin.actions.platforms.telegram.run_process", run)

    class Delegate:
        def execute(self, request: ActionRequest) -> ActionResult:
            return ActionResult(request.key, ActionOutcome.LAUNCH_ACCEPTED)

    class Verifier(StubChatVerifier):
        def ready(self) -> bool:
            return True

        def verify(self, app_id: str, pid: int, target: str = "Saved Messages") -> bool:
            return False

        def find_visible_control(
            self, app_id: str, pid: int, label: str
        ) -> VisibleControlTarget:

            return VisibleControlTarget(50, 100, 100, 20, 1000, 750, geometry=geometry)

    generic = desktop_control.DesktopControlExecutor(
        Delegate(),
        identity_reader=lambda: ("org.telegram.desktop", 42),
        token_reader=lambda: "window-7",
        verifier=Verifier(),
    )
    generic.execute(
        ActionRequest(
            ActionKey(0, 1),
            CommandIntent(
                CommandKind.VISIBLE_CONTROL,
                "Settings",
                control_observation=WindowObservation(
                    "org.telegram.desktop",
                    42,
                    "window-7",
                    "initial-1",
                    monotonic(),
                    monotonic() + 9,
                ),
            ),
        )
    )
    telegram = TelegramSavedMessagesExecutor(
        Delegate(),
        telegram_desktop_id="org.telegram.desktop",
        identity_reader=lambda: ("org.telegram.desktop", 42),
        verifier=Verifier(),
    )
    telegram._click_result(
        ActionRequest(
            ActionKey(0, 2),
            CommandIntent(CommandKind.OPEN_CHAT, "Ali", app="telegram"),
        ),
        ("org.telegram.desktop", 42),
        "Ali",
        ChatSearchMatch(
            50,
            100,
            100,
            20,
            1000,
            750,
            geometry,
            ((50, 100, 100, 20), (300, 100, 40, 15)),
        ),
        visible_row=True,
    )
    assert sent[0][-1] == sent[1][-1] == "geometry=" + geometry.to_json()
    assert json.loads(sent[1][-2].removeprefix("evidence=")) == [
        [50, 100, 100, 20],
        [300, 100, 40, 15],
    ]


def test_stable_telegram_row_must_be_in_the_same_window() -> None:
    from dataclasses import replace

    geometry = CaptureGeometry(
        "logical_desktop",
        0,
        (0, 0, 800, 600),
        (800, 600),
        1,
        1,
        (0, 0, 0, 0),
        (0, 0),
        (1, 1),
        "window-7",
        "capture-1",
        100.0,
        (0, 0, 800, 600),
    )
    first = ChatSearchMatch(50, 100, 100, 20, 800, 600, geometry)
    second = ChatSearchMatch(
        50,
        100,
        100,
        20,
        800,
        600,
        replace(geometry, window_token="window-8", capture_id="capture-2"),
    )
    assert not _same_search_box(first, second)
