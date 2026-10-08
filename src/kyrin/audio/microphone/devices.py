"""Resolve a saved microphone name to the current PortAudio device index."""

import json
from dataclasses import dataclass
from typing import Any, Protocol

from kyrin.audio.audio_format import AudioFormat, AudioSampleFormat
from kyrin.audio.microphone.errors import MicrophoneError


@dataclass(frozen=True, slots=True)
class MicrophoneDevice:
    key: str
    label: str
    index: int


@dataclass(frozen=True, slots=True)
class MicrophoneConfiguration:
    index: int
    audio_format: AudioFormat
    frames_per_chunk: int


class MicrophoneResolver(Protocol):
    def list_inputs(self) -> tuple[MicrophoneDevice, ...]: ...

    def resolve(self, key: str | None) -> MicrophoneConfiguration: ...


def microphone_key(host_api: str, name: str) -> str:
    """Encode a human-readable device identity without saving a volatile index."""
    if not host_api.strip() or not name.strip():
        raise ValueError("microphone host API and name must not be empty")
    return json.dumps([host_api, name], ensure_ascii=False, separators=(",", ":"))


def _parse_key(key: str) -> tuple[str, str]:
    try:
        value: object = json.loads(key)
    except json.JSONDecodeError as exc:
        raise MicrophoneError("saved microphone selection is invalid") from exc
    if (
        not isinstance(value, list)
        or len(value) != 2
        or not all(isinstance(item, str) and item.strip() for item in value)
    ):
        raise MicrophoneError("saved microphone selection is invalid")
    return value[0], value[1]


def _sounddevice() -> Any:
    # Import only when an application actually needs audio hardware.
    try:
        import sounddevice as sd  # type: ignore[import-untyped]
    except Exception as exc:
        # PortAudio may initialize during import and raise its own exception
        # before the module exposes that exception type to this caller.
        raise MicrophoneError("audio runtime could not start") from exc

    return sd


class PortAudioMicrophoneResolver:
    """Resolve afresh on each attempt; missing or ambiguous devices fail closed."""

    def list_inputs(self) -> tuple[MicrophoneDevice, ...]:
        sd = _sounddevice()
        try:
            host_apis = sd.query_hostapis()
            devices = sd.query_devices()
        except (sd.PortAudioError, OSError, ValueError) as exc:
            raise MicrophoneError("microphone devices could not be listed") from exc
        available: list[MicrophoneDevice] = []
        for index, device in enumerate(devices):
            if int(device["max_input_channels"]) <= 0:
                continue
            host_api = str(host_apis[int(device["hostapi"])]["name"])
            name = str(device["name"])
            available.append(
                MicrophoneDevice(
                    microphone_key(host_api, name),
                    f"{name} ({host_api})",
                    index,
                )
            )
        return tuple(available)

    def resolve(self, key: str | None) -> MicrophoneConfiguration:
        sd = _sounddevice()
        try:
            if key is None:
                index = int(sd.default.device[0])
            else:
                host_api, name = _parse_key(key)
                expected = microphone_key(host_api, name)
                matches = tuple(
                    item.index for item in self.list_inputs() if item.key == expected
                )
                if not matches:
                    raise MicrophoneError("selected microphone is not available")
                if len(matches) > 1:
                    raise MicrophoneError("selected microphone is ambiguous")
                index = matches[0]
            if index < 0:
                raise MicrophoneError("default microphone is not configured")
            details = sd.query_devices(index, "input")
            sample_rate = int(round(details["default_samplerate"]))
            sd.check_input_settings(
                device=index, channels=1, dtype="int16", samplerate=sample_rate
            )
        except MicrophoneError:
            raise
        except (sd.PortAudioError, OSError, ValueError, TypeError) as exc:
            raise MicrophoneError("selected microphone could not be opened") from exc
        return MicrophoneConfiguration(
            index,
            AudioFormat(sample_rate, 1, AudioSampleFormat.INT16),
            max(1, round(sample_rate * 0.02)),
        )
