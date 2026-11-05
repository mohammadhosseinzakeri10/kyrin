"""L01 acceptance tooling uses real composition boundaries without hardware."""

from pathlib import Path
from typing import cast

import pytest

from kyrin.app.events import AudioCaptureReady
from kyrin.app.platforms import ubuntu
from kyrin.app.settings import AllowedApp, AppSettings, SttSelection
from kyrin.commands.models import ResponseChannel
from kyrin.responses.presenter import PresentedResponse
from kyrin.stt.contracts import SpeechToTextEngine
from kyrin.stt.transcript import TranscriptStatus, TranscriptUpdate
from scripts.audio.accept_l01 import Evidence, safe_settings
from scripts.audio.l01_stability import run_cycle
from tests.app.test_ubuntu_session_factory import (
    FakeDetector,
    FakeEngine,
    FakeMicrophones,
    FakeSpeechController,
    _catalog,
)


@pytest.mark.parametrize("aec", [False, True])
def test_synthetic_long_silence_wait_controls_and_next_session(aec: bool) -> None:
    # Ninety seconds of synthetic PCM, processed quickly with a logical clock.
    first = run_cycle(90, aec=aec)
    second = run_cycle(1, aec=aec)
    assert first["turns"] == second["turns"] == 4
    assert first["errors"] == second["errors"] == []
    assert cast(float, first["logical_seconds"]) > 90


def test_acceptance_never_records_content() -> None:
    evidence = Evidence()
    evidence.observe(TranscriptUpdate(0, "PRIVATE_TEXT", TranscriptStatus.FINAL))
    evidence.observe(
        PresentedResponse(
            None, None, "PRIVATE_REPLY", ResponseChannel.TEXT_AND_VOICE, "en"
        )
    )
    for index in range(300):
        evidence.observe(
            TranscriptUpdate(index + 1, "PRIVATE_TEXT", TranscriptStatus.FINAL)
        )
    report = evidence.snapshot()
    assert "PRIVATE" not in str(report)
    assert len(cast(list[object], report["recent"])) == 256
    assert report["counts"] == {"final": 301}
    evidence.record("explicit_control", control="standby")
    for _ in range(300):
        evidence.record("understanding_finished")
    transitions = cast(list[dict[str, object]], evidence.snapshot()["transitions"])
    assert len(transitions) == 1
    assert transitions[0]["kind"] == "explicit_control"
    assert transitions[0]["control"] == "standby"
    for _ in range(1100):
        evidence.record("explicit_control", control="start")
    assert evidence.snapshot()["transitions_dropped"] == 77
    evidence.observe(AudioCaptureReady("fixture", generation=3))
    latest = cast(list[dict[str, object]], evidence.snapshot()["transitions"])[-1]
    assert latest["kind"] == "capture_ready"
    assert latest["generation"] == 3


def test_owner_acceptance_composition_cannot_create_executor_or_portal(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def forbidden(*args: object, **kwargs: object) -> None:
        raise AssertionError("desktop/history side effect in acceptance")

    saved = AppSettings(
        stt=SttSelection("fake", tmp_path / "model", "en"),
        action_execution_enabled=True,
        history_enabled=True,
        system_power_enabled=True,
        trust_all_capabilities=True,
        allow_desktop_scroll=True,
        allow_desktop_control=True,
        allowed_apps=(AllowedApp("telegram", "telegram.desktop"),),
        allowed_chat_apps=("telegram",),
        allowed_close_apps=("telegram",),
        allowed_window_apps=("telegram",),
    )
    monkeypatch.setattr(ubuntu, "SpeechSessionController", FakeSpeechController)
    monkeypatch.setattr(ubuntu, "DesktopInputBroker", forbidden)
    monkeypatch.setattr(ubuntu, "default_history_path", forbidden)
    from kyrin.model_resources import MemorySnapshot, ModelResources

    factory = ubuntu.UbuntuSessionFactory(
        stt_openers={"fake": lambda _: cast(SpeechToTextEngine, FakeEngine())},
        on_event=lambda _: None,
        microphones=FakeMicrophones(),
        detector_factory=FakeDetector,
        catalog=_catalog(tmp_path),
        executor_factory=forbidden,  # type: ignore[arg-type]
        model_resources=ModelResources(memory=lambda: MemorySnapshot()),
    )
    with factory(safe_settings(saved)) as runtime:
        runtime.run()
    assert saved.action_execution_enabled and saved.history_enabled
    assert saved.allowed_chat_apps == ("telegram",)


def test_live_tool_writes_pending_report_with_fake_session_only(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import io
    import json
    from collections.abc import Iterator
    from contextlib import contextmanager

    from kyrin.app.controller import RuntimeSession
    from scripts.audio import accept_l01

    class Session:
        def run(self) -> None:
            pass

        def stop(self) -> None:
            pass

    @contextmanager
    def session(_settings: AppSettings) -> Iterator[RuntimeSession]:
        yield Session()

    saved = AppSettings(
        tts_enabled=False, stt=SttSelection("fake", tmp_path / "PRIVATE_MODEL", "en")
    )
    monkeypatch.setattr(
        "scripts.audio.accept_l01.JsonSettingsStore.load", lambda _: saved
    )
    monkeypatch.setattr(accept_l01, "UbuntuSessionFactory", lambda **_: session)
    monkeypatch.setattr(
        accept_l01,
        "source_snapshot",
        lambda: {"sha256": "synthetic_test", "stable_during_capture": True},
    )
    monkeypatch.setattr(accept_l01, "ROOT", tmp_path)
    monkeypatch.setattr(
        "scripts.audio.accept_l01.kyrin.__file__",
        str(tmp_path / "src/kyrin/__init__.py"),
    )
    stdin = io.StringIO("quit\n")
    monkeypatch.setattr("scripts.audio.accept_l01.sys.stdin", stdin)
    monkeypatch.setattr(
        "scripts.audio.accept_l01.select.select", lambda *_: ([stdin], [], [])
    )
    path = tmp_path / "local-data/result.json"
    monkeypatch.setattr(
        "scripts.audio.accept_l01.sys.argv", ["accept_l01", "--output", str(path)]
    )
    assert accept_l01.main() == 0
    report = json.loads(path.read_text())
    assert report["status"] == "live_evidence_pending_review"
    assert report["desktop"] == "dry_run_no_executor_no_portal"
    assert report["cleanup_confirmed"]
    assert report["source_unchanged"]
    assert report["scenarios"]["natural"] == "not_run"
    assert report["actual_test_seconds"] <= report["actual_seconds_including_cleanup"]


@pytest.fixture
def isolated_tool(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    import io

    from scripts.audio import accept_l01

    saved = AppSettings(
        tts_enabled=False, stt=SttSelection("fake", tmp_path / "model", "en")
    )
    monkeypatch.setattr(
        "scripts.audio.accept_l01.JsonSettingsStore.load", lambda _: saved
    )
    monkeypatch.setattr(
        accept_l01,
        "source_snapshot",
        lambda: {"sha256": "synthetic_test", "stable_during_capture": True},
    )
    monkeypatch.setattr(accept_l01, "ROOT", tmp_path)
    monkeypatch.setattr(
        "scripts.audio.accept_l01.kyrin.__file__",
        str(tmp_path / "src/kyrin/__init__.py"),
    )
    stdin = io.StringIO("quit\n")
    monkeypatch.setattr("scripts.audio.accept_l01.sys.stdin", stdin)
    monkeypatch.setattr(
        "scripts.audio.accept_l01.select.select", lambda *_: ([stdin], [], [])
    )
    path = tmp_path / "local-data/result.json"
    monkeypatch.setattr(
        "scripts.audio.accept_l01.sys.argv", ["accept_l01", "--output", str(path)]
    )
    return path


@pytest.mark.parametrize("broken_cleanup", [False, True])
def test_tool_detects_quiet_runtime_failure_or_unconfirmed_resources(
    isolated_tool: Path,
    monkeypatch: pytest.MonkeyPatch,
    broken_cleanup: bool,
) -> None:
    import json
    from collections.abc import Iterator
    from contextlib import contextmanager
    from threading import Event

    from kyrin.app.controller import RuntimeSession
    from kyrin.model_resources import MemorySnapshot, ModelResources
    from scripts.audio import accept_l01

    ran = Event()
    resources = ModelResources(memory=lambda: MemorySnapshot())
    monkeypatch.setattr(accept_l01, "ModelResources", lambda: resources)

    class Session:
        def run(self) -> None:
            if broken_cleanup:
                resources.block()
                ran.set()
            else:
                ran.set()
                raise RuntimeError("PRIVATE_BACKEND_MESSAGE")

        def stop(self) -> None:
            pass

    @contextmanager
    def factory(_settings: AppSettings) -> Iterator[RuntimeSession]:
        yield Session()

    monkeypatch.setattr(accept_l01, "UbuntuSessionFactory", lambda **_: factory)

    def ready(*args: object) -> tuple[list[object], list[object], list[object]]:
        assert ran.wait(2)
        import sys

        return [sys.stdin], [], []

    monkeypatch.setattr("scripts.audio.accept_l01.select.select", ready)
    assert accept_l01.main() == 1
    report = json.loads(isolated_tool.read_text())
    if broken_cleanup:
        assert report["cleanup_confirmed"] is False
    else:
        assert report["error"] == "RuntimeError"
    assert "PRIVATE" not in isolated_tool.read_text()


@pytest.mark.parametrize("boundary", ["initial", "final"])
def test_tool_preserves_failure_report_when_source_probe_fails(
    isolated_tool: Path,
    monkeypatch: pytest.MonkeyPatch,
    boundary: str,
) -> None:
    import json
    import logging
    from collections.abc import Iterator
    from contextlib import contextmanager

    from kyrin.app.controller import RuntimeSession
    from scripts.audio import accept_l01

    class Session:
        def run(self) -> None:
            pass

        def stop(self) -> None:
            pass

    @contextmanager
    def factory(_settings: AppSettings) -> Iterator[RuntimeSession]:
        yield Session()

    calls = 0

    def snapshot() -> dict[str, object]:
        nonlocal calls
        calls += 1
        if calls == (1 if boundary == "initial" else 2):
            raise OSError("PRIVATE_PROBE_MESSAGE")
        return {"sha256": "synthetic_test", "stable_during_capture": True}

    monkeypatch.setattr(accept_l01, "UbuntuSessionFactory", lambda **_: factory)
    monkeypatch.setattr(accept_l01, "source_snapshot", snapshot)
    previous = logging.root.manager.disable
    try:
        assert accept_l01.main() == 1
        report = json.loads(isolated_tool.read_text())
        assert report["error"] == "OSError"
        assert report["status"] != "initializing"
        assert report["source_unchanged"] is False
        assert "PRIVATE" not in isolated_tool.read_text()
        assert logging.root.manager.disable == previous
    finally:
        logging.disable(previous)


def test_child_audit_does_not_treat_unreadable_owned_process_as_exited(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from scripts.audio.accept_l01 import ChildAudit

    original = Path.read_text

    def read(path: Path, *args: object, **kwargs: object) -> str:
        if path == Path("/proc/123/stat"):
            raise PermissionError("PRIVATE_PROC_MESSAGE")
        return original(path)

    monkeypatch.setattr(Path, "read_text", read)
    audit = ChildAudit()
    audit.observed[123] = "42"
    assert audit.remaining() == []
    assert audit.unverified == {123}
    assert audit.errors["identity_unavailable"] == 1


def test_later_pass_cannot_erase_a_failed_acceptance_cycle(
    isolated_tool: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import io
    import json
    from collections.abc import Iterator
    from contextlib import contextmanager

    from kyrin.app.controller import RuntimeSession
    from scripts.audio import accept_l01

    class Session:
        def run(self) -> None:
            pass

        def stop(self) -> None:
            pass

    @contextmanager
    def factory(_settings: AppSettings) -> Iterator[RuntimeSession]:
        yield Session()

    stdin = io.StringIO("fail silence\npass silence\nquit\n")
    monkeypatch.setattr(accept_l01, "UbuntuSessionFactory", lambda **_: factory)
    monkeypatch.setattr("scripts.audio.accept_l01.sys.stdin", stdin)
    monkeypatch.setattr(
        "scripts.audio.accept_l01.select.select", lambda *_: ([stdin], [], [])
    )
    accept_l01.main()
    report = json.loads(isolated_tool.read_text())
    assert report["scenarios"]["silence"] == "fail"
    assert report["scenario_counts"]["silence"] == {"pass": 1, "fail": 1, "skip": 0}


def test_tool_reports_rejected_tts_queue(
    isolated_tool: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import io
    import json
    from collections.abc import Iterator
    from contextlib import contextmanager

    from kyrin.app.controller import RuntimeSession
    from scripts.audio import accept_l01

    class Session:
        def run(self) -> None:
            pass

        def stop(self) -> None:
            pass

    @contextmanager
    def factory(_settings: AppSettings) -> Iterator[RuntimeSession]:
        yield Session()

    stdin = io.StringIO("tts\nquit\n")
    monkeypatch.setattr(accept_l01, "UbuntuSessionFactory", lambda **_: factory)
    monkeypatch.setattr("scripts.audio.accept_l01.sys.stdin", stdin)
    monkeypatch.setattr(
        "scripts.audio.accept_l01.select.select", lambda *_: ([stdin], [], [])
    )
    monkeypatch.setattr(
        "scripts.audio.accept_l01.ResponseSpeaker.submit", lambda *_: False
    )
    assert accept_l01.main() == 1
    report = json.loads(isolated_tool.read_text())
    assert report["observations"]["counts"]["tts_error"] == 1
    assert report["error"] == "tts_queue_rejected"
