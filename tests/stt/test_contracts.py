"""Different local recognizers must fit the same audio-facing contract."""

from collections.abc import Sequence

import pytest

from kyrin.audio.audio_data import AudioData
from kyrin.audio.audio_format import AudioFormat, AudioSampleFormat
from kyrin.stt.capabilities import SpeechToTextCapabilities
from kyrin.stt.contracts import SpeechToTextEngine, SpeechToTextSession
from kyrin.stt.device import ComputeDevice, DevicePreference, SpeechToTextOptions
from kyrin.stt.errors import DeviceUnavailableError, SpeechToTextError
from kyrin.stt.transcript import TranscriptStatus, TranscriptUpdate

FORMAT = AudioFormat(16000, 1, AudioSampleFormat.INT16)
CHUNK = AudioData(bytes(320), FORMAT)


class PartialSession:
    input_format = FORMAT
    supports_partial_updates = True

    def __init__(self, compute_device: ComputeDevice) -> None:
        self.compute_device = compute_device
        self.closed = False

    def accept_audio(self, chunk: AudioData) -> Sequence[TranscriptUpdate]:
        assert chunk.audio_format == self.input_format
        return (TranscriptUpdate(0, "open Tele", TranscriptStatus.PARTIAL),)

    def finish(self) -> Sequence[TranscriptUpdate]:
        return (TranscriptUpdate(0, "open Telegram", TranscriptStatus.FINAL),)

    def close(self) -> None:
        self.closed = True


class PartialEngine:
    capabilities = SpeechToTextCapabilities(
        supported_devices=frozenset({ComputeDevice.CPU, ComputeDevice.GPU}),
        supported_languages=frozenset({"en", "fa"}),
        supports_partial_updates=True,
        supports_language_detection=True,
    )

    def open_session(self, options: SpeechToTextOptions) -> SpeechToTextSession:
        device = (
            ComputeDevice.CPU
            if options.device is DevicePreference.CPU
            else ComputeDevice.GPU
        )
        return PartialSession(device)

    def close(self) -> None:
        pass


class FinalOnlySession:
    input_format = FORMAT
    compute_device = ComputeDevice.CPU
    supports_partial_updates = False

    def __init__(self) -> None:
        self.closed = False

    def accept_audio(self, chunk: AudioData) -> Sequence[TranscriptUpdate]:
        assert chunk.audio_format == self.input_format
        return ()

    def finish(self) -> Sequence[TranscriptUpdate]:
        return (TranscriptUpdate(0, "open Telegram", TranscriptStatus.FINAL),)

    def close(self) -> None:
        self.closed = True


class FinalOnlyEngine:
    capabilities = SpeechToTextCapabilities(
        supported_devices=frozenset({ComputeDevice.CPU}),
        supported_languages=frozenset({"en"}),
        supports_partial_updates=False,
        supports_language_detection=False,
    )

    def open_session(self, options: SpeechToTextOptions) -> SpeechToTextSession:
        if options.device is DevicePreference.GPU:
            raise DeviceUnavailableError("GPU is unavailable")
        return FinalOnlySession()

    def close(self) -> None:
        pass


def consume_one_chunk(
    engine: SpeechToTextEngine, options: SpeechToTextOptions
) -> tuple[ComputeDevice, bool, list[TranscriptUpdate]]:
    try:
        session = engine.open_session(options)
        try:
            assert session.input_format == CHUNK.audio_format
            updates = list(session.accept_audio(CHUNK))
            updates.extend(session.finish())
            return session.compute_device, session.supports_partial_updates, updates
        finally:
            session.close()
    finally:
        engine.close()


def test_partial_gpu_and_final_only_cpu_engines_share_one_consumer() -> None:
    assert PartialEngine().capabilities.supported_languages == frozenset({"en", "fa"})
    assert FinalOnlyEngine().capabilities.supported_devices == frozenset(
        {ComputeDevice.CPU}
    )
    gpu, partial, streaming_updates = consume_one_chunk(
        PartialEngine(), SpeechToTextOptions(device=DevicePreference.GPU)
    )
    cpu, final_only, cpu_updates = consume_one_chunk(
        FinalOnlyEngine(), SpeechToTextOptions(device=DevicePreference.AUTO)
    )

    assert (gpu, partial) == (ComputeDevice.GPU, True)
    assert (cpu, final_only) == (ComputeDevice.CPU, False)
    assert [update.status for update in streaming_updates] == [
        TranscriptStatus.PARTIAL,
        TranscriptStatus.FINAL,
    ]
    assert {update.segment_id for update in streaming_updates} == {0}
    assert cpu_updates == [TranscriptUpdate(0, "open Telegram", TranscriptStatus.FINAL)]


def test_explicit_unavailable_gpu_is_reported() -> None:
    with pytest.raises(DeviceUnavailableError, match="GPU is unavailable"):
        consume_one_chunk(
            FinalOnlyEngine(), SpeechToTextOptions(device=DevicePreference.GPU)
        )

    assert issubclass(DeviceUnavailableError, SpeechToTextError)


def test_explicit_cpu_is_used_by_a_dual_device_engine() -> None:
    device, partial, updates = consume_one_chunk(
        PartialEngine(), SpeechToTextOptions(device=DevicePreference.CPU)
    )

    assert device is ComputeDevice.CPU
    assert partial
    assert updates[-1].status is TranscriptStatus.FINAL


def test_contract_values_reject_invalid_metadata() -> None:
    with pytest.raises(ValueError, match="language_hint"):
        SpeechToTextOptions(language_hint=" ")
    with pytest.raises(ValueError, match="vocabulary_hints"):
        SpeechToTextOptions(vocabulary_hints=(" ",))
    with pytest.raises(ValueError, match="vocabulary_hints"):
        SpeechToTextOptions(vocabulary_hints=("name\ncommand",))
    with pytest.raises(ValueError, match="segment_id"):
        TranscriptUpdate(-1, "text", TranscriptStatus.PARTIAL)
    with pytest.raises(ValueError, match="language"):
        TranscriptUpdate(0, "text", TranscriptStatus.FINAL, language=" ")
    with pytest.raises(ValueError, match="supported_devices"):
        SpeechToTextCapabilities(frozenset(), None, False, False)
