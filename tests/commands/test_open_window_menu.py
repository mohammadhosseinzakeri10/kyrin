"""Voice window switching names only exact registered applications."""

from pathlib import Path

import pytest

from kyrin.commands.coordinator import CommandCoordinator
from kyrin.commands.demo_interpreter import DemoCommandInterpreter
from kyrin.commands.model_interpreter import ModelAssistedInterpreter
from kyrin.commands.models import (
    CommandIntent,
    CommandKind,
    CommandResolution,
    ResponseKind,
    ResponseRequest,
)
from kyrin.commands.understanding import (
    MeaningStep,
    ProposedMeaning,
    RequestedOperation,
    UnderstandingResult,
    UnderstandingStatus,
)
from kyrin.desktop.platforms.xdg import XdgDesktopAppCatalog
from kyrin.desktop.spoken_app_names import CatalogSpokenAppResolver
from kyrin.stt.transcript import TranscriptStatus, TranscriptUpdate


def _final(index: int, text: str) -> TranscriptUpdate:
    return TranscriptUpdate(index, text, TranscriptStatus.FINAL, "en")


def _coordinator(tmp_path: Path) -> CommandCoordinator:
    apps = tmp_path / "applications"
    apps.mkdir()
    (apps / "telegram.desktop").write_text(
        "[Desktop Entry]\nType=Application\nName=Telegram\n", encoding="utf-8"
    )
    names = CatalogSpokenAppResolver(
        XdgDesktopAppCatalog((tmp_path,)), {"telegram.desktop": "telegram"}
    )
    rules = DemoCommandInterpreter(
        names, allowed_window_apps=frozenset({"telegram"})
    )
    class OverviewModel:
        def understand(self, source, *, context):
            return UnderstandingResult(
                UnderstandingStatus.READY,
                (ProposedMeaning((MeaningStep(RequestedOperation.SHOW_ALL_WINDOWS),)),),
            )

    return CommandCoordinator(ModelAssistedInterpreter(
        rules, OverviewModel(), names,
        allowed_apps=frozenset({"telegram"}),
        supported_chat_apps=frozenset(),
        action_review=rules.review_model_action,
    ))


@pytest.mark.parametrize("utterance", (
    "Show all open windows",
    "Show all open apps",
    "Let me see every running application window",
    "تمام صفحات برنامه‌های باز را نشان بده",
    "Montre toutes les fenêtres ouvertes",
))
def test_semantic_request_then_choose_by_number_or_name(
    tmp_path: Path, utterance: str
) -> None:
    coordinator = _coordinator(tmp_path)
    shown = coordinator.observe(_final(0, utterance))
    assert shown[0].intent is not None
    assert shown[0].intent.kind is CommandKind.SHOW_ALL_WINDOWS
    assert isinstance(shown[1], ResponseRequest)
    assert shown[1].window_count == 99
    selected = coordinator.observe(_final(1, "number two"))
    assert isinstance(selected[0], CommandResolution)
    assert selected[0].intent is not None
    assert selected[0].intent.window_index == 2
    coordinator.observe(_final(2, "Show my open windows"))
    by_name = coordinator.observe(_final(3, "Telegram"))
    assert by_name[0].intent is not None
    assert by_name[0].intent.kind is CommandKind.SELECT_OPEN_APP_WINDOW
    assert by_name[0].intent.target == "telegram"


def test_unknown_name_and_cancel_do_not_activate(tmp_path: Path) -> None:
    coordinator = _coordinator(tmp_path)
    coordinator.observe(_final(0, "Show open windows"))
    unknown = coordinator.observe(_final(1, "A random application"))
    assert unknown[0].intent is None
    cancelled = coordinator.observe(_final(2, "cancel"))
    assert cancelled[0].intent is not None
    assert cancelled[0].intent.kind is CommandKind.HIDE_APP_WINDOWS


@pytest.mark.parametrize("phrase", (
    "close number two", "exit number 2", "quit two", "close 2",
    "close the second window", "number two close", "شماره دو را ببند",
    "دومی را ببند", "ببند پنجره ۲", "شماره دو ببند",
    "please close window 2",
))
def test_numbered_close_requires_confirmation(tmp_path: Path, phrase: str) -> None:
    coordinator = _coordinator(tmp_path)
    coordinator.observe(_final(0, "Show all open windows"))
    asked = coordinator.observe(_final(1, phrase))
    assert asked[0].intent is None
    assert asked[1].kind is ResponseKind.CONFIRM_NUMBERED_CLOSE
    assert asked[1].window_index == 2
    approved = coordinator.observe(_final(2, "yes"))
    assert approved[0].intent is not None
    assert approved[0].intent == CommandIntent(
        CommandKind.CLOSE_SHOWN_WINDOW, "desktop", window_index=2
    )


def test_numbered_close_cancellation_and_invalid_number(tmp_path: Path) -> None:
    coordinator = _coordinator(tmp_path)
    coordinator.observe(_final(0, "Show all open windows"))
    invalid = coordinator.observe(_final(1, "close number 100"))
    assert invalid[0].intent is None
    assert invalid[1].kind is ResponseKind.CHOOSE_WINDOW
    coordinator.observe(_final(2, "close one"))
    assert coordinator.observe(_final(3, "no"))[0].intent is None
    later = coordinator.observe(_final(4, "number two"))[0].intent
    assert later == CommandIntent(
        CommandKind.SELECT_APP_WINDOW, "desktop", window_index=2
    )


@pytest.mark.parametrize("utterance", (
    "Show all installed apps",
    "Show all browser tabs",
    "Do not show all open windows",
    "همه پنجره‌ها را نشان نده",
    "همه پنجره‌ها را نشان بده و تلگرام را باز کن",
    "تمام صفحات را نشان بده",
))
def test_bad_model_proposal_cannot_turn_other_or_negative_requests_into_overview(
    tmp_path: Path, utterance: str
) -> None:
    coordinator = _coordinator(tmp_path)
    result = coordinator.observe(_final(0, utterance))
    assert result[0].intent is None
