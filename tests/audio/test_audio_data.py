import dataclasses

import pytest

from kyrin.audio.audio_data import AudioData
from kyrin.audio.audio_format import AudioFormat, AudioSampleFormat


def test_audio_data_stores_values() -> None:
    data = b"test audio"

    audio_format = AudioFormat(
        sample_rate=16000,
        channels=1,
        sample_format=AudioSampleFormat.INT16,
    )

    audio_data = AudioData(
        data=data,
        audio_format=audio_format,
    )

    assert audio_data.data == data
    assert audio_data.audio_format == audio_format


def test_audio_data_is_immutable() -> None:
    audio_format = AudioFormat(
        sample_rate=16000,
        channels=1,
        sample_format=AudioSampleFormat.INT16,
    )

    audio_data = AudioData(
        data=b"test audio",
        audio_format=audio_format,
    )

    with pytest.raises(dataclasses.FrozenInstanceError):
        audio_data.data = b"new data"  # type: ignore[misc]

    with pytest.raises(dataclasses.FrozenInstanceError):
        audio_data.audio_format = AudioFormat(  # type: ignore[misc]
            sample_rate=48000,
            channels=2,
            sample_format=AudioSampleFormat.FLOAT32,
        )


def test_audio_data_rejects_misaligned_data() -> None:
    audio_format = AudioFormat(
        sample_rate=16000,
        channels=1,
        sample_format=AudioSampleFormat.INT16,
    )

    with pytest.raises(ValueError):
        AudioData(
            data=b"\x00\x01\x02",
            audio_format=audio_format,
        )
