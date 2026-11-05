"""Exercise production synthesis with native inference and playback replaced."""

import json
from pathlib import Path
from threading import Event
from typing import Any
from unittest.mock import MagicMock

import pytest

from kyrin.commands.models import CommandContext
from kyrin.model_resources import ModelResources, Workload
from kyrin.stt.device import DevicePreference
from kyrin.tts import runtime as tts_runtime
from kyrin.tts.models import TtsSelection
from scripts.commands import measure_model_composition as composition
from scripts.commands.evaluation_contract import DEFAULT_PLAN, fingerprint
from scripts.commands.measure_model_composition import SilentPlayback


def test_synthesis_releases_shared_admission_before_inert_playback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    silent = SilentPlayback()
    adapter = MagicMock()
    adapter.provider.return_value = "cpu"
    adapter.load.return_value = object()
    adapter.generate.return_value = ([0.0] * 20, 16000)
    monkeypatch.setitem(tts_runtime._ADAPTERS, "kokoro", adapter)
    monkeypatch.setattr(tts_runtime, "validate_tts_selection", lambda selection: None)
    model = tts_runtime.LocalTtsModel("kokoro", tmp_path / "model.onnx")
    monkeypatch.setattr(tts_runtime, "inspect_tts_model", lambda path: model)
    resources = ModelResources()

    def playback_module(name: str) -> SilentPlayback:
        assert name == "sounddevice"
        with resources.use(Workload.COMMAND):
            pass
        return silent

    monkeypatch.setattr(tts_runtime, "import_module", playback_module)
    synth = tts_runtime.ConfiguredSpeechSynthesizer(
        TtsSelection(
            backend="kokoro",
            model_path=tmp_path,
            voice="0",
            device=DevicePreference.CPU,
        ),
        resources=resources,
    )
    synth.speak("This is a safe benchmark.", "en")
    assert silent.calls == [{"samples": 20, "sample_rate": 16000}]
    assert synth.close()


def test_composition_binds_existing_artifacts_and_rejects_drift(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plan: dict[str, Any] = json.loads(DEFAULT_PLAN.read_text())
    profile = plan["profiles"][-1]
    selected = {}
    for part in ("stt", "tts"):
        path = tmp_path / part
        path.mkdir()
        profile["composition"][part]["artifact"] = str(path)
        selected[part] = {"model_path": str(path)}
    inventory = {"environment": {"technical_selection": {"value": selected}}}
    observed = {
        "models": {"value": [{"tag": "qwen3.5:9b", "manifest_sha256": "a" * 64}]}
    }
    monkeypatch.setattr(composition, "environment_snapshot", lambda *args: observed)
    bound, stt, tts = composition.composition_selection(plan, inventory)
    assert bound["model"]["artifact_sha256"] == "a" * 64
    assert profile["model"]["artifact_sha256"] is None
    assert (stt, tts) == (tmp_path / "stt", tmp_path / "tts")
    profile["model"]["artifact_sha256"] = "b" * 64
    with pytest.raises(ValueError, match="artifact"):
        composition.composition_selection(plan, inventory)
    profile["model"]["artifact_sha256"] = None
    selected["stt"]["model_path"] = str(tmp_path / "other")
    with pytest.raises(ValueError, match="artifact"):
        composition.composition_selection(plan, inventory)


@pytest.mark.parametrize("failure", ["failed", "cleanup"])
def test_composition_stops_after_failed_command_or_cleanup(failure: str) -> None:
    row: dict[str, Any] = {
        "status": "failed" if failure == "failed" else "completed",
        "model": "test:1",
        "requests": [],
        "device_reports": [],
    }
    if failure == "cleanup":
        row["requests"].append({"kind": "cleanup"})
    with pytest.raises(RuntimeError, match="stop subsequent"):
        composition.require_command_success(row)


def test_composition_conditions_have_distinct_profiles_without_mutation() -> None:
    plan = json.loads(DEFAULT_PLAN.read_text())
    profile = plan["profiles"][-1]
    original = json.dumps(profile, sort_keys=True)
    alone = composition.condition_profile(profile, "command_alone")
    idle = composition.condition_profile(profile, "stt_resident_idle")
    active = composition.condition_profile(profile, "command_waiting_for_tts")
    assert alone["composition"]["stt"]["activity"] == "off"
    assert idle["composition"]["stt"]["activity"] == "idle"
    assert active["composition"]["tts"]["activity"] == "text"
    assert len({fingerprint(p) for p in (alone, idle, active)}) == 3
    assert json.dumps(profile, sort_keys=True) == original


@pytest.mark.parametrize("queued", [False, True])
def test_failed_command_is_saved_and_native_thread_finishes_with_inert_playback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, queued: bool
) -> None:
    monkeypatch.setattr(composition, "ROOT", tmp_path)
    data = tmp_path / "datasets/commands"
    data.mkdir(parents=True)
    (data / "l04_audio_cases.jsonl").write_text(
        json.dumps(
            {
                "id": "test",
                "audio_path": "test.wav",
                "sha256": "a" * 64,
                "spoken_reference": "Open Telegram",
            }
        )
        + "\n"
    )
    plan = tmp_path / "plan.json"
    plan.write_text("{}")
    profile = json.loads(DEFAULT_PLAN.read_text())["profiles"][-1]
    monkeypatch.setattr(
        composition,
        "composition_selection",
        lambda *args: (profile, tmp_path / "stt", tmp_path / "tts"),
    )
    monkeypatch.setattr(composition, "file_hash", lambda path: "a" * 64)
    monkeypatch.setattr(composition, "source_snapshot", lambda: {"sha256": "test"})
    monkeypatch.setattr(composition, "get_json", lambda url: {"version": "0.31.1"})
    server = MagicMock()
    server.__enter__.return_value = "http://127.0.0.1:1"
    monkeypatch.setattr(composition, "LocalOllamaServer", lambda *args: server)
    engine = MagicMock()
    failed = Event()
    native_finished = Event()
    calls = 0

    def understand(*args: Any, **kwargs: Any) -> CommandContext:
        nonlocal calls
        calls += 1
        if not queued or calls == 4:
            failed.set()
            raise RuntimeError("inference failed")
        return CommandContext()

    engine.understand.side_effect = understand
    monkeypatch.setattr(composition, "MeasuredEngine", lambda *args: engine)
    stt = MagicMock()
    stt.return_value.close.return_value = None
    monkeypatch.setattr(composition, "ManagedSttEngine", stt)
    monkeypatch.setattr(
        composition, "evaluate_item", lambda *args, **kwargs: CommandContext()
    )
    adapter = MagicMock()

    def native_generate() -> tuple[list[float], int]:
        assert failed.wait(2)
        assert isinstance(
            tts_runtime.__dict__["import_module"]("sounddevice"), SilentPlayback
        )
        native_finished.set()
        return [], 16000

    adapter.generate.side_effect = native_generate
    monkeypatch.setitem(tts_runtime._ADAPTERS, "kokoro", adapter)
    synth = MagicMock()
    synth.speak.side_effect = lambda *args: adapter.generate()
    synth.close.side_effect = lambda: native_finished.is_set()
    monkeypatch.setattr(
        composition, "ConfiguredSpeechSynthesizer", lambda *args, **kwargs: synth
    )
    monkeypatch.setattr(composition, "running_device", lambda *args: CommandContext())
    # Memory monitoring remains a real thread, with hardware probes replaced.
    monkeypatch.setattr(
        "scripts.commands.measure_command_models.memory_sample", lambda roots: {}
    )
    output = tmp_path / "local-data/run"
    composition.run(plan, plan, output, 10)
    result = json.loads((output / "run.json").read_text())
    rows = result["results"]
    assert any(row.get("status") == "failed" for row in rows)
    assert any(row["condition"] == "composition_error" for row in rows)
    if queued:
        assert native_finished.is_set()
        assert next(row for row in rows if row["condition"] == "tts_close")["released"]
        assert (
            next(row for row in rows if row["condition"] == "tts_text")["errors"] == []
        )
    else:
        stt.assert_not_called()
