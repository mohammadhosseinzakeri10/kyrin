"""No real power requests: shared saved consent and stale worker checks."""

from collections.abc import Callable
from dataclasses import replace

import pytest

from kyrin.app.permissions import PermissionPolicy
from kyrin.app.settings import AppSettings
from kyrin.system_power import flow


@pytest.mark.parametrize("change", ["none", "cancel", "revoke", "expire"])
@pytest.mark.parametrize("trust", [False, True])
def test_saved_power_permission_does_not_prompt_and_late_worker_cannot_act(
    monkeypatch: pytest.MonkeyPatch,
    change: str,
    trust: bool,
) -> None:
    jobs: list[Callable[[], None]] = []
    actions: list[flow.PowerAction] = []
    prompts: list[flow.PowerPrompt] = []
    now = [10.0]

    class Thread:
        def __init__(
            self,
            *,
            target: Callable[[flow.PowerPrompt], None],
            args: tuple[flow.PowerPrompt],
            daemon: bool,
        ) -> None:
            self.run = lambda: target(*args)

        def start(self) -> None:
            jobs.append(self.run)

    class Backend:
        def work_warning(self, action: flow.PowerAction) -> str:
            pytest.fail("saved consent must not enter the old confirmation flow")

        def request(self, action: flow.PowerAction) -> None:
            actions.append(action)

    monkeypatch.setattr(flow, "Thread", Thread)
    settings = AppSettings(
        action_execution_enabled=True,
        trust_all_capabilities=trust,
        system_power_enabled=not trust,
    )
    policy = PermissionPolicy(settings)
    power = flow.SystemPowerFlow(
        Backend(),
        prompts.append,
        enabled=True,
        permissions=policy,
        clock=lambda: now[0],
    )
    assert power.on_final_speech("Restart this computer")
    assert not any(
        item.stage
        in (flow.PowerStage.FIRST, flow.PowerStage.SECOND, flow.PowerStage.CHECKING)
        for item in prompts
    )
    if change == "cancel":
        power.cancel()
    elif change == "revoke":
        power.configure(
            enabled=False,
            permissions=PermissionPolicy(
                replace(
                    settings, trust_all_capabilities=False, system_power_enabled=False
                )
            ),
        )
    elif change == "expire":
        now[0] += 46
    jobs.pop()()
    assert bool(actions) == (change == "none")
    assert not power.respond(prompts[0].request_id, "yes")


def test_missing_power_grant_never_dispatches() -> None:
    class Backend:
        def work_warning(self, action: flow.PowerAction) -> str:
            pytest.fail("denied power request inspected the backend")

        def request(self, action: flow.PowerAction) -> None:
            pytest.fail("denied power request dispatched")

    power = flow.SystemPowerFlow(
        Backend(),
        lambda _: None,
        enabled=True,
        permissions=PermissionPolicy(AppSettings()),
    )
    assert not power.start(flow.PowerAction.RESTART)
