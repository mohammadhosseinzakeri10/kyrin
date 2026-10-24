"""Real adapter boundaries with fake STT, TTS and playback."""

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from kyrin.model_resources import (
    MemorySnapshot,
    ModelResources,
    ResourceLimits,
    Workload,
)
from kyrin.stt.contracts import TurnAwareSpeechToTextSession
from kyrin.stt.device import ComputeDevice, DevicePreference, SpeechToTextOptions
from kyrin.stt.resources import ManagedSttEngine
from kyrin.tts import runtime
from kyrin.tts.models import TtsSelection


def test_stt_keeps_selected_engine_across_turns_and_cancel_bypasses_admission() -> None:
    calls: list[object] = []
    resources = ModelResources(memory=lambda: MemorySnapshot())

    class Session:
        input_format = object()
        compute_device = ComputeDevice.GPU
        supports_partial_updates = True

        def accept_audio(self, chunk: object) -> tuple[()]:
            calls.append(chunk)
            return ()

        def start_turn(self) -> tuple[()]:
            calls.append("start")
            return ()

        def end_turn(self) -> tuple[()]:
            calls.append("end")
            return ()

        def finish(self) -> tuple[()]:
            return ()

        def close(self) -> None:
            calls.append("session close")

    class Engine:
        capabilities = object()

        def open_session(self, options: SpeechToTextOptions) -> Session:
            calls.append(options)
            return Session()

        def cancel_pending_inference(self) -> None:
            calls.append("cancel")

        def close(self) -> None:
            calls.append("engine close")

    def load() -> Any:
        calls.append("load")
        return Engine()

    engine = ManagedSttEngine(load, resources, "stt:selected:gpu")
    options = SpeechToTextOptions(device=DevicePreference.GPU)
    session = engine.open_session(options)
    assert session.compute_device is ComputeDevice.GPU
    assert isinstance(session, TurnAwareSpeechToTextSession)
    for _ in range(2):
        session.start_turn()
        session.end_turn()
    assert calls.count("load") == 1
    assert calls[1] is options
    assert "stt:selected:gpu" in resources._residents
    with resources.use(Workload.OCR):
        engine.cancel_pending_inference()
    session.close()
    engine.close()
    assert calls[-3:] == ["cancel", "session close", "engine close"]
    assert not resources._residents


@pytest.mark.parametrize("device", [DevicePreference.AUTO, DevicePreference.GPU])
def test_tts_reloads_after_oom_and_releases_before_playback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, device: DevicePreference
) -> None:
    resources = ModelResources(
        ResourceLimits(wait_seconds=0.01), memory=lambda: MemorySnapshot()
    )
    calls: list[str] = []
    providers: list[DevicePreference] = []

    class Model:
        def close(self) -> None:
            calls.append("close")

    class Adapter:
        def provider(self, selection: TtsSelection) -> str:
            providers.append(selection.device)
            return selection.device.value

        def load(self, *args: object) -> Model:
            calls.append("load")
            return Model()

        def generate(self, *args: object) -> tuple[list[float], int]:
            if calls.count("load") == 1:
                raise MemoryError("fake OOM")
            return [0.1], 16000

    def play(*args: object, **kwargs: object) -> None:
        assert calls[-1] == "close"
        # A playing response must not own model admission and block listening.
        with resources.use(Workload.STT):
            calls.append("play")

    monkeypatch.setattr(runtime, "validate_tts_selection", lambda selection: None)
    monkeypatch.setattr(runtime, "inspect_tts_model", lambda folder: object())
    monkeypatch.setitem(runtime._ADAPTERS, "kitten", Adapter())
    monkeypatch.setattr(
        runtime,
        "import_module",
        lambda name: SimpleNamespace(play=play, wait=lambda: None),
    )
    synth = runtime.ConfiguredSpeechSynthesizer(
        TtsSelection("kitten", tmp_path, "0", device=device), resources=resources
    )
    with pytest.raises(MemoryError, match="fake OOM"):
        synth.speak("hello", "en")
    synth.speak("again", "en")
    assert calls == ["load", "close", "load", "close", "play"]
    assert (
        providers
        == [DevicePreference.CPU if device is DevicePreference.AUTO else device] * 2
    )
    assert not synth._loaded
