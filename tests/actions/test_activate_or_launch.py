"""Existing app activation is verified before claiming success."""

from collections.abc import Iterator

import pytest

from kyrin.actions.activate_or_launch import ActivateOrLaunchExecutor
from kyrin.actions.models import ActionKey, ActionOutcome, ActionRequest, ActionResult
from kyrin.commands.models import CommandIntent, CommandKind
from kyrin.desktop.app_activation import ActivationAttempt

REQUEST = ActionRequest(
    ActionKey(0, 0), CommandIntent(CommandKind.OPEN_APP, "telegram"), "en"
)


class FakeLauncher:
    def __init__(self) -> None:
        self.calls: list[ActionRequest] = []

    def execute(self, request: ActionRequest) -> ActionResult:
        self.calls.append(request)
        return ActionResult(request.key, ActionOutcome.LAUNCH_ACCEPTED)


class FakeActivator:
    def __init__(self, outcome: ActivationAttempt) -> None:
        self.outcome = outcome
        self.calls: list[str] = []

    def activate_existing_app(self, app_id: str) -> ActivationAttempt:
        self.calls.append(app_id)
        return self.outcome


class FakeObserver:
    def __init__(self, values: tuple[str | None, ...]) -> None:
        self.values: Iterator[str | None] = iter(values)
        self.calls = 0

    def observe_active_app(self) -> str | None:
        self.calls += 1
        return next(self.values)


def test_existing_window_is_raised_and_confirmed_without_relaunch() -> None:
    launcher = FakeLauncher()
    activator = FakeActivator(ActivationAttempt.REQUESTED)
    observer = FakeObserver(("browser", "telegram"))
    result = ActivateOrLaunchExecutor(
        launcher, activator, observer, retry_delay_s=0
    ).execute(REQUEST)
    assert result == ActionResult(
        REQUEST.key, ActionOutcome.CONFIRMED, observed_active_app="telegram"
    )
    assert activator.calls == ["telegram"]
    assert launcher.calls == []
    assert observer.calls == 2


def test_missing_window_uses_existing_launcher() -> None:
    launcher = FakeLauncher()
    result = ActivateOrLaunchExecutor(
        launcher, FakeActivator(ActivationAttempt.NO_WINDOW), FakeObserver(())
    ).execute(REQUEST)
    assert result.outcome is ActionOutcome.LAUNCH_ACCEPTED
    assert launcher.calls == [REQUEST]


def test_multiple_windows_without_selected_target_never_launches() -> None:
    launcher = FakeLauncher()
    result = ActivateOrLaunchExecutor(
        launcher,
        FakeActivator(ActivationAttempt.MULTIPLE_WINDOWS),
        FakeObserver(()),
    ).execute(REQUEST)
    assert result == ActionResult(
        REQUEST.key, ActionOutcome.FAILED, error_code="multiple_windows"
    )
    assert launcher.calls == []


@pytest.mark.parametrize(
    ("attempt", "error_code"),
    [
        (ActivationAttempt.UNKNOWN, "activation_unknown"),
        (ActivationAttempt.REQUESTED, "activation_unverified"),
    ],
)
def test_uncertain_activation_never_relaunches(
    attempt: ActivationAttempt, error_code: str
) -> None:
    launcher = FakeLauncher()
    result = ActivateOrLaunchExecutor(
        launcher,
        FakeActivator(attempt),
        FakeObserver((None, None, None, None)),
        retry_delay_s=0,
    ).execute(REQUEST)
    assert result == ActionResult(
        REQUEST.key, ActionOutcome.UNKNOWN, error_code=error_code
    )
    assert launcher.calls == []


def test_other_actions_keep_the_existing_executor() -> None:
    launcher = FakeLauncher()
    activator = FakeActivator(ActivationAttempt.REQUESTED)
    request = ActionRequest(
        ActionKey(0, 1),
        CommandIntent(CommandKind.OPEN_CHAT, "Saved Messages", "telegram"),
    )
    ActivateOrLaunchExecutor(launcher, activator, FakeObserver(())).execute(request)
    assert activator.calls == []
    assert launcher.calls == [request]
