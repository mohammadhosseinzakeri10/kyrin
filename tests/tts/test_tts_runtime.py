"""Deterministic checks for local TTS selection and playback routing."""

from importlib import util
from pathlib import Path
from threading import Event, Thread
from time import monotonic
from types import SimpleNamespace

import pytest

from kyrin.app.settings import TtsLanguageRoute, TtsSelection
from kyrin.responses.speech import SpeechSynthesisError
from kyrin.stt.device import DevicePreference
from kyrin.tts.runtime import (
    ConfiguredSpeechSynthesizer,
    LocalTtsModel,
    inspect_tts_model,
    kitten_model_file,
    register_tts_adapter,
    validate_tts_selection,
)


def _kitten_folder(folder: Path) -> Path:
    folder.mkdir()
    for filename in ("model.int8.onnx", "voices.bin", "tokens.txt"):
        (folder / filename).write_bytes(b"model fixture")
    (folder / "espeak-ng-data").mkdir()
    return folder


def test_kitten_package_requires_all_local_files(tmp_path: Path) -> None:
    folder = _kitten_folder(tmp_path / "kitten-voice")
    assert kitten_model_file(folder).name == "model.int8.onnx"
    (folder / "voices.bin").unlink()
    with pytest.raises(ValueError, match="voices.bin"):
        kitten_model_file(folder)


def test_preview_passes_draft_speed_without_changing_saved_selection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    synthesizer = ConfiguredSpeechSynthesizer(TtsSelection())
    selected = TtsSelection("qwen3tts", tmp_path, "0", 1.35)
    calls: list[tuple[str, TtsSelection, str]] = []
    monkeypatch.setattr(
        synthesizer,
        "_speak_model",
        lambda text, choice, language: calls.append((text, choice, language)),
    )
    synthesizer.speak_preview("Hello", "en-US", selected)
    assert calls == [("Hello", selected, "en-us")]
    assert synthesizer._selection == TtsSelection()


def test_gpu_choice_is_rejected_when_cuda_runtime_is_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    folder = _kitten_folder(tmp_path / "voice")
    monkeypatch.setattr("kyrin.tts.runtime.isolated_runtime_python", lambda _: None)
    monkeypatch.setattr("kyrin.tts.runtime.util.find_spec", lambda _: object())
    providers = SimpleNamespace(
        get_available_providers=lambda: ["CPUExecutionProvider"]
    )
    monkeypatch.setattr("kyrin.tts.runtime.import_module", lambda _: providers)
    with pytest.raises(ValueError, match="GPU runtime is unavailable"):
        validate_tts_selection(
            TtsSelection("kitten", folder, "0", 1.0, DevicePreference.GPU)
        )


def test_preview_reports_missing_gpu_runtime_instead_of_generic_playback_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    folder = _kitten_folder(tmp_path / "voice")
    monkeypatch.setattr("kyrin.tts.runtime.isolated_runtime_python", lambda _: None)
    monkeypatch.setattr("kyrin.tts.runtime.util.find_spec", lambda _: object())
    providers = SimpleNamespace(
        get_available_providers=lambda: ["CPUExecutionProvider"]
    )
    monkeypatch.setattr("kyrin.tts.runtime.import_module", lambda _: providers)
    synthesizer = ConfiguredSpeechSynthesizer(TtsSelection())
    selection = TtsSelection("kitten", folder, "0", 1.0, DevicePreference.GPU)

    with pytest.raises(SpeechSynthesisError, match="GPU runtime is unavailable"):
        synthesizer.speak_preview("Hello", "en", selection)


def test_kokoro_gpu_uses_isolated_sherpa_worker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from kyrin.tts import runtime as tts_runtime

    folder = tmp_path / "kokoro-test"
    _kitten_folder(folder)
    (folder / "lexicon-us-en.txt").write_bytes(b"fixture")
    runtime_python = tmp_path / "sherpa-gpu/bin/python"
    calls: list[tuple[object, ...]] = []

    class FakeWorker:
        def __init__(
            self, python: Path, family: str, path: Path, provider: str
        ) -> None:
            calls.append((python, family, path, provider))

        def generate(
            self, text: str, voice: str, speed: float, language: str
        ) -> tuple[list[float], int]:
            calls.append((text, voice, speed, language))
            return [0.2], 24000

    monkeypatch.setattr(util, "find_spec", lambda _: object())
    monkeypatch.setattr(
        tts_runtime, "isolated_runtime_python", lambda _: runtime_python
    )
    monkeypatch.setattr(
        tts_runtime,
        "probe_isolated_runtime",
        lambda python, family, device: calls.append((python, family, device)),
    )
    monkeypatch.setattr(tts_runtime, "IsolatedTtsWorker", FakeWorker)
    selection = TtsSelection("kokoro", folder, "3", 1.0, DevicePreference.GPU)
    validate_tts_selection(selection)
    adapter = next(
        item for item in tts_runtime.available_tts_adapters() if item.key == "kokoro"
    )
    provider = adapter.provider(selection)
    assert provider == "gpu"
    loaded = adapter.load(inspect_tts_model(folder), folder, provider)
    assert adapter.generate(loaded, "Hello", "3", 1.0, "en") == ([0.2], 24000)
    assert calls == [
        (runtime_python, "kokoro", "gpu"),
        (runtime_python, "kokoro", folder, "gpu"),
        ("Hello", "3", 1.0, "en"),
    ]


def test_kitten_uses_selected_voice_speed_and_releases_model_between_calls(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    folder = _kitten_folder(tmp_path / "voice")
    generated: list[tuple[str, int, float]] = []
    played: list[tuple[object, int, bool]] = []
    created: list[object] = []

    class FakeTts:
        def __init__(self, config: object) -> None:
            created.append(config)

        def generate(self, *, text: str, sid: int, speed: float) -> object:
            generated.append((text, sid, speed))
            return SimpleNamespace(samples=[1, 2], sample_rate=24000)

    fake_sherpa = SimpleNamespace(
        OfflineTtsKittenModelConfig=lambda **kwargs: SimpleNamespace(**kwargs),
        OfflineTtsModelConfig=lambda **kwargs: SimpleNamespace(**kwargs),
        OfflineTtsConfig=lambda **kwargs: SimpleNamespace(
            **kwargs, validate=lambda: True
        ),
        OfflineTts=FakeTts,
    )
    fake_playback = SimpleNamespace(
        play=lambda samples, rate, *, blocking: played.append(
            (samples, rate, blocking)
        ),
        wait=lambda: None,
    )
    monkeypatch.setattr("kyrin.tts.runtime.util.find_spec", lambda _: object())
    monkeypatch.setattr(
        "kyrin.tts.runtime.import_module",
        lambda name: fake_sherpa if name == "sherpa_onnx" else fake_playback,
    )
    synthesizer = ConfiguredSpeechSynthesizer(
        TtsSelection("kitten", folder, "2", 1.15, DevicePreference.CPU)
    )
    synthesizer.speak("Hello", "en")
    synthesizer.speak("Again", "en-US")

    assert generated == [("Hello", 2, 1.15), ("Again", 2, 1.15)]
    assert played == [([1, 2], 24000, False)] * 2
    assert len(created) == 2
    assert not synthesizer._loaded


def test_persian_vits_route_loads_local_piper_package(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    folder = tmp_path / "vits-piper-fa_IR-gyro-medium"
    folder.mkdir()
    for name in ("fa_IR-gyro-medium.onnx", "tokens.txt"):
        (folder / name).write_bytes(b"fixture")
    (folder / "espeak-ng-data").mkdir()
    assert inspect_tts_model(folder).family == "vits"
    configured: list[object] = []
    generated: list[tuple[str, int, float]] = []

    class FakeTts:
        num_speakers = 1

        def __init__(self, config: object) -> None:
            configured.append(config)

        def generate(self, *, text: str, sid: int, speed: float) -> object:
            generated.append((text, sid, speed))
            return SimpleNamespace(samples=[0.1], sample_rate=22050)

    fake_sherpa = SimpleNamespace(
        OfflineTtsVitsModelConfig=lambda **kwargs: SimpleNamespace(**kwargs),
        OfflineTtsModelConfig=lambda **kwargs: SimpleNamespace(**kwargs),
        OfflineTtsConfig=lambda **kwargs: SimpleNamespace(
            **kwargs, validate=lambda: True
        ),
        OfflineTts=FakeTts,
    )
    fake_playback = SimpleNamespace(
        play=lambda *args, **kwargs: None, wait=lambda: None
    )
    monkeypatch.setattr("kyrin.tts.runtime.util.find_spec", lambda _: object())
    monkeypatch.setattr(
        "kyrin.tts.runtime.import_module",
        lambda name: fake_sherpa if name == "sherpa_onnx" else fake_playback,
    )
    synthesizer = ConfiguredSpeechSynthesizer(
        TtsSelection(),
        (
            TtsLanguageRoute(
                "fa", TtsSelection("vits", folder, "0", 1.1, DevicePreference.CPU)
            ),
        ),
    )
    synthesizer.speak("سلام کایرین", "fa-IR")
    assert generated == [("سلام کایرین", 0, 1.1)]
    assert len(configured) == 1


def test_kokoro_package_is_detected_and_uses_its_lexicon(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    folder = tmp_path / "kokoro-multi-lang-v1_1"
    folder.mkdir()
    for name in ("model.onnx", "tokens.txt", "voices.bin", "lexicon-us-en.txt"):
        (folder / name).write_bytes(b"fixture")
    (folder / "espeak-ng-data").mkdir()
    assert inspect_tts_model(folder).family == "kokoro"
    options: list[dict[str, object]] = []

    class FakeTts:
        num_speakers = 103

        def __init__(self, config: object) -> None:
            pass

        def generate(self, *, text: str, sid: int, speed: float) -> object:
            assert (text, sid, speed) == ("Hello", 42, 1.0)
            return SimpleNamespace(samples=[0.1], sample_rate=24000)

    def kokoro_config(**kwargs: object) -> object:
        options.append(kwargs)
        return SimpleNamespace(**kwargs)

    fake_sherpa = SimpleNamespace(
        OfflineTtsKokoroModelConfig=kokoro_config,
        OfflineTtsModelConfig=lambda **kwargs: SimpleNamespace(**kwargs),
        OfflineTtsConfig=lambda **kwargs: SimpleNamespace(
            **kwargs, validate=lambda: True
        ),
        OfflineTts=FakeTts,
    )
    monkeypatch.setattr("kyrin.tts.runtime.util.find_spec", lambda _: object())
    monkeypatch.setattr(
        "kyrin.tts.runtime.import_module",
        lambda name: (
            fake_sherpa
            if name == "sherpa_onnx"
            else SimpleNamespace(play=lambda *args, **kwargs: None, wait=lambda: None)
        ),
    )
    ConfiguredSpeechSynthesizer(
        TtsSelection("kokoro", folder, "42", 1.0, DevicePreference.CPU)
    ).speak("Hello", "en")
    assert options[0]["lexicon"] == str(folder / "lexicon-us-en.txt")


def test_kokoro_package_rejects_missing_lexicon(tmp_path: Path) -> None:
    folder = _kitten_folder(tmp_path / "kokoro-missing-lexicon")
    with pytest.raises(ValueError, match="lexicon"):
        inspect_tts_model(folder)


def test_failed_synthesis_disposes_worker_before_retry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from kyrin.tts import runtime as tts_runtime

    folder = tmp_path / "faulty-voice"
    folder.mkdir()
    (folder / "voice.dat").write_bytes(b"fixture")
    monkeypatch.setattr(tts_runtime, "_ADAPTERS", tts_runtime._ADAPTERS.copy())
    created: list[object] = []
    closed: list[object] = []

    class FakeWorker:
        def close(self) -> None:
            closed.append(self)

    class FakeAdapter:
        key = "faultyvoice"
        label = "Faulty voice"

        def inspect(self, path: Path) -> tts_runtime.LocalTtsModel | None:
            if path == folder:
                return tts_runtime.LocalTtsModel(self.key, path / "voice.dat")
            return None

        def validate(self, selection: TtsSelection, model: object) -> None:
            pass

        def provider(self, selection: TtsSelection) -> str:
            return "cuda:0"

        def load(self, model: object, path: Path, provider: str) -> FakeWorker:
            worker = FakeWorker()
            created.append(worker)
            return worker

        def generate(
            self, loaded: FakeWorker, text: str, voice: str, speed: float, language: str
        ) -> tuple[list[float], int]:
            if len(created) == 1:
                raise SpeechSynthesisError("CUDA failure")
            return [0.1], 24000

    tts_runtime.register_tts_adapter(FakeAdapter())
    monkeypatch.setattr(
        tts_runtime,
        "import_module",
        lambda name: SimpleNamespace(
            play=lambda *args, **kwargs: None, wait=lambda: None
        ),
    )
    synthesizer = ConfiguredSpeechSynthesizer(
        TtsSelection("faultyvoice", folder, "0", 1.0, DevicePreference.GPU)
    )
    with pytest.raises(SpeechSynthesisError, match="CUDA failure"):
        synthesizer.speak("Hello", "en")
    assert closed == [created[0]]
    synthesizer.speak("Hello again", "en")
    assert len(created) == 2


@pytest.mark.parametrize(
    ("old_device", "new_device"),
    (
        (DevicePreference.GPU, DevicePreference.CPU),
        (DevicePreference.CPU, DevicePreference.GPU),
    ),
)
def test_device_switch_releases_old_tts_model_before_loading_new_one(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    old_device: DevicePreference,
    new_device: DevicePreference,
) -> None:
    from kyrin.tts import runtime as tts_runtime

    folder = tmp_path / "switchable-voice"
    folder.mkdir()
    (folder / "voice.dat").write_bytes(b"fixture")
    monkeypatch.setattr(tts_runtime, "_ADAPTERS", tts_runtime._ADAPTERS.copy())
    events: list[str] = []
    released = Event()

    class FakeModel:
        def __init__(self, provider: str) -> None:
            self.provider = provider

        def close(self) -> None:
            events.append(f"close {self.provider}")
            released.set()

    class FakeAdapter:
        key = "switchablevoice"
        label = "Switchable voice"

        def inspect(self, path: Path) -> tts_runtime.LocalTtsModel | None:
            if path == folder:
                return tts_runtime.LocalTtsModel(self.key, path / "voice.dat")
            return None

        def validate(self, selection: TtsSelection, model: object) -> None:
            pass

        def provider(self, selection: TtsSelection) -> str:
            return selection.device.value

        def load(self, model: object, path: Path, provider: str) -> FakeModel:
            events.append(f"load {provider}")
            return FakeModel(provider)

        def generate(
            self,
            loaded: FakeModel,
            text: str,
            voice: str,
            speed: float,
            language: str,
        ) -> tuple[list[float], int]:
            return [0.1], 16000

    tts_runtime.register_tts_adapter(FakeAdapter())
    monkeypatch.setattr(
        tts_runtime,
        "import_module",
        lambda name: SimpleNamespace(
            play=lambda *args, **kwargs: None, wait=lambda: None
        ),
    )
    old_selection = TtsSelection("switchablevoice", folder, "0", 1.0, old_device)
    new_selection = TtsSelection("switchablevoice", folder, "0", 1.0, new_device)
    synthesizer = ConfiguredSpeechSynthesizer(old_selection)
    synthesizer.speak("Hello", "en")
    synthesizer.configure(new_selection)
    assert released.wait(2)
    synthesizer.speak("Hello again", "en")
    assert events == [
        f"load {old_device.value}",
        f"close {old_device.value}",
        f"load {new_device.value}",
        f"close {new_device.value}",
    ]
    synthesizer.close()
    assert events[-1] == f"close {new_device.value}"


def test_quit_stops_active_isolated_tts_worker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from kyrin.tts import runtime as tts_runtime

    folder = tmp_path / "busy-voice"
    folder.mkdir()
    (folder / "voice.dat").write_bytes(b"fixture")
    monkeypatch.setattr(tts_runtime, "_ADAPTERS", tts_runtime._ADAPTERS.copy())
    started = Event()
    released = Event()
    closed = Event()
    errors: list[SpeechSynthesisError] = []

    class FakeWorker:
        def close(self) -> None:
            closed.set()
            released.set()

        def generate(self) -> tuple[list[float], int]:
            started.set()
            assert released.wait(2)
            raise SpeechSynthesisError("worker stopped")

    class FakeAdapter:
        key = "busyvoice"
        label = "Busy voice"

        def inspect(self, path: Path) -> tts_runtime.LocalTtsModel | None:
            if path == folder:
                return tts_runtime.LocalTtsModel(self.key, path / "voice.dat")
            return None

        def validate(self, selection: TtsSelection, model: object) -> None:
            pass

        def provider(self, selection: TtsSelection) -> str:
            return "gpu"

        def load(self, model: object, path: Path, provider: str) -> FakeWorker:
            return FakeWorker()

        def generate(
            self,
            loaded: FakeWorker,
            text: str,
            voice: str,
            speed: float,
            language: str,
        ) -> tuple[list[float], int]:
            return loaded.generate()

    tts_runtime.register_tts_adapter(FakeAdapter())
    monkeypatch.setattr(tts_runtime, "IsolatedTtsWorker", FakeWorker)
    synthesizer = ConfiguredSpeechSynthesizer(
        TtsSelection("busyvoice", folder, "0", 1.0, DevicePreference.GPU)
    )

    def speak() -> None:
        try:
            synthesizer.speak("Hello", "en")
        except SpeechSynthesisError as error:
            errors.append(error)

    speech_thread = Thread(target=speak)
    speech_thread.start()
    assert started.wait(2)
    synthesizer.close()
    speech_thread.join(2)

    assert not speech_thread.is_alive()
    assert closed.is_set()
    assert len(errors) == 1


def test_quit_does_not_wait_forever_for_stuck_in_process_tts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from kyrin.tts import runtime as tts_runtime

    folder = tmp_path / "busy-cpu-voice"
    folder.mkdir()
    (folder / "voice.dat").write_bytes(b"fixture")
    monkeypatch.setattr(tts_runtime, "_ADAPTERS", tts_runtime._ADAPTERS.copy())
    started = Event()
    release = Event()
    model_closed = Event()

    class FakeModel:
        def close(self) -> None:
            model_closed.set()

    class FakeAdapter:
        key = "busycpuvoice"
        label = "Busy CPU voice"

        def inspect(self, path: Path) -> tts_runtime.LocalTtsModel | None:
            if path == folder:
                return tts_runtime.LocalTtsModel(self.key, path / "voice.dat")
            return None

        def validate(self, selection: TtsSelection, model: object) -> None:
            pass

        def provider(self, selection: TtsSelection) -> str:
            return "cpu"

        def load(self, model: object, path: Path, provider: str) -> FakeModel:
            return FakeModel()

        def generate(
            self,
            loaded: FakeModel,
            text: str,
            voice: str,
            speed: float,
            language: str,
        ) -> tuple[list[float], int]:
            started.set()
            assert release.wait(5)
            return [0.1], 16000

    tts_runtime.register_tts_adapter(FakeAdapter())
    synthesizer = ConfiguredSpeechSynthesizer(
        TtsSelection("busycpuvoice", folder, "0", 1.0, DevicePreference.CPU)
    )
    thread = Thread(target=lambda: synthesizer.speak("Hello", "en"), daemon=True)
    thread.start()
    try:
        assert started.wait(2)
        before = monotonic()
        assert synthesizer.close() is False
        assert monotonic() - before < 3
        assert not model_closed.is_set()
    finally:
        release.set()
        thread.join(2)
    assert not thread.is_alive()


def test_packaged_adapter_can_add_a_new_family_without_changing_playback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from kyrin.tts import runtime as tts_runtime

    monkeypatch.setattr(tts_runtime, "_ADAPTERS", tts_runtime._ADAPTERS.copy())
    folder = tmp_path / "custom-voice"
    folder.mkdir()
    model_file = folder / "voice.dat"
    model_file.write_bytes(b"fixture")
    calls: list[object] = []

    class FakeAdapter:
        key = "customvoice"
        label = "Custom voice"

        def inspect(self, path: Path) -> LocalTtsModel | None:
            if (path / "voice.dat").is_file():
                return tts_runtime.LocalTtsModel(self.key, path / "voice.dat")
            return None

        def validate(self, selection: TtsSelection, model: object) -> None:
            calls.append("validated")

        def provider(self, selection: TtsSelection) -> str:
            return "cpu"

        def load(self, model: object, path: Path, provider: str) -> object:
            calls.append((path, provider))
            return object()

        def generate(
            self, loaded: object, text: str, voice: str, speed: float, language: str
        ) -> tuple[list[float], int]:
            calls.append((text, voice, speed, language))
            return [0.1], 16000

    register_tts_adapter(FakeAdapter())
    monkeypatch.setattr(
        tts_runtime,
        "import_module",
        lambda _: SimpleNamespace(
            play=lambda *args, **kwargs: calls.append("played"),
            wait=lambda: None,
        ),
    )
    selection = TtsSelection("customvoice", folder, "0", 1.0, DevicePreference.CPU)
    assert inspect_tts_model(folder).family == "customvoice"
    ConfiguredSpeechSynthesizer(selection).speak("Hello", "en")
    assert calls == ["validated", (folder, "cpu"), ("Hello", "0", 1.0, "en"), "played"]


def test_stale_model_prompt_is_discarded_after_generation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    folder = _kitten_folder(tmp_path / "kitten-voice")
    current = True
    played: list[object] = []

    class FakeTts:
        def __init__(self, config: object) -> None:
            pass

        def generate(self, *, text: str, sid: int, speed: float) -> object:
            nonlocal current
            current = False
            return SimpleNamespace(samples=[0.1], sample_rate=16000)

    fake_sherpa = SimpleNamespace(
        OfflineTtsKittenModelConfig=lambda **kwargs: SimpleNamespace(**kwargs),
        OfflineTtsModelConfig=lambda **kwargs: SimpleNamespace(**kwargs),
        OfflineTtsConfig=lambda **kwargs: SimpleNamespace(
            **kwargs, validate=lambda: True
        ),
        OfflineTts=FakeTts,
    )
    monkeypatch.setattr("kyrin.tts.runtime.util.find_spec", lambda _: object())
    monkeypatch.setattr(
        "kyrin.tts.runtime.import_module",
        lambda name: (
            fake_sherpa
            if name == "sherpa_onnx"
            else SimpleNamespace(play=lambda *args, **kwargs: played.append(args))
        ),
    )
    synthesizer = ConfiguredSpeechSynthesizer(
        TtsSelection("kitten", folder, "0", 1.0, DevicePreference.CPU)
    )
    synthesizer.speak_if_current("Old stage", "en", lambda: current)

    assert played == []


def test_unsupported_package_is_rejected_instead_of_loaded(tmp_path: Path) -> None:
    folder = tmp_path / "unknown"
    folder.mkdir()
    (folder / "weights.bin").write_bytes(b"fixture")
    with pytest.raises(ValueError, match="Unsupported TTS package family"):
        inspect_tts_model(folder)


def test_interrupt_during_synthesis_discards_late_audio_and_keeps_input_open(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from kyrin.tts import runtime

    folder = _kitten_folder(tmp_path / "voice")
    entered, release = Event(), Event()
    played: list[object] = []

    class Adapter:
        def provider(self, selection: TtsSelection) -> str:
            return "cpu"

        def load(self, *args: object) -> object:
            return object()

        def generate(self, *args: object) -> tuple[list[float], int]:
            entered.set()
            assert release.wait(2)
            return [0.1], 16000

    monkeypatch.setattr(runtime, "inspect_tts_model", lambda folder: object())
    monkeypatch.setitem(runtime._ADAPTERS, "kitten", Adapter())
    monkeypatch.setattr(runtime, "validate_tts_selection", lambda selection: None)
    monkeypatch.setattr(
        runtime,
        "import_module",
        lambda name: SimpleNamespace(
            play=lambda *args, **kwargs: played.append(args),
            wait=lambda: None,
        ),
    )
    synth = ConfiguredSpeechSynthesizer(TtsSelection("kitten", folder, "0"))
    worker = Thread(target=synth.speak, args=("hello", "en"))
    worker.start()
    try:
        assert entered.wait(2)
        assert not synth.is_playing
        synth.interrupt()
    finally:
        release.set()
        worker.join(2)
    assert not worker.is_alive()
    assert played == []
