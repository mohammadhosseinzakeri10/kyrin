"""Saved microphone identities resolve without requiring audio hardware."""

import builtins
from types import SimpleNamespace

import pytest

from kyrin.audio.microphone import devices
from kyrin.audio.microphone.errors import MicrophoneError


class FakePortAudio:
    class PortAudioError(Exception):
        pass

    def __init__(self, *, duplicate: bool = False) -> None:
        self.default = SimpleNamespace(device=(1, 0))
        self.inputs = [
            {
                "name": "Speakers",
                "hostapi": 0,
                "max_input_channels": 0,
                "default_samplerate": 48000,
            },
            {
                "name": "USB Mic",
                "hostapi": 0,
                "max_input_channels": 1,
                "default_samplerate": 44100,
            },
        ]
        if duplicate:
            self.inputs.append(dict(self.inputs[1]))
        self.checked: list[int] = []

    def query_hostapis(self) -> list[dict[str, str]]:
        return [{"name": "PulseAudio"}]

    def query_devices(
        self, device: int | None = None, kind: str | None = None
    ) -> list[dict[str, object]] | dict[str, object]:
        if device is None:
            return self.inputs
        assert kind == "input"
        return self.inputs[device]

    def check_input_settings(
        self, *, device: int, channels: int, dtype: str, samplerate: int
    ) -> None:
        assert (channels, dtype, samplerate) == (1, "int16", 44100)
        self.checked.append(device)


def test_default_and_selected_microphone_resolve_at_current_index(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = FakePortAudio()
    monkeypatch.setattr(devices, "_sounddevice", lambda: fake)
    resolver = devices.PortAudioMicrophoneResolver()

    available = resolver.list_inputs()
    assert len(available) == 1
    assert available[0].label == "USB Mic (PulseAudio)"
    assert resolver.resolve(None).index == 1
    selected = resolver.resolve(available[0].key)
    assert selected.index == 1
    assert selected.audio_format.sample_rate == 44100
    assert selected.frames_per_chunk == 882
    assert selected.device_key == available[0].key
    assert resolver.resolve(None).device_key == available[0].key
    assert fake.checked == [1, 1, 1]


def test_missing_ambiguous_and_malformed_selection_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = FakePortAudio(duplicate=True)
    monkeypatch.setattr(devices, "_sounddevice", lambda: fake)
    resolver = devices.PortAudioMicrophoneResolver()

    with pytest.raises(MicrophoneError, match="ambiguous"):
        resolver.resolve(devices.microphone_key("PulseAudio", "USB Mic"))
    with pytest.raises(MicrophoneError, match="not available"):
        resolver.resolve(devices.microphone_key("PulseAudio", "Other Mic"))
    with pytest.raises(MicrophoneError, match="invalid"):
        resolver.resolve("not-a-device-key")
    assert fake.checked == []


def test_native_audio_initialization_failure_is_reported_as_microphone_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_import = builtins.__import__

    def failing_import(name: str, *args: object, **kwargs: object) -> object:
        if name == "sounddevice":
            raise RuntimeError("PortAudio initialization failed")
        return original_import(name, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(builtins, "__import__", failing_import)
        with pytest.raises(MicrophoneError, match="runtime could not start"):
            devices.PortAudioMicrophoneResolver().list_inputs()
