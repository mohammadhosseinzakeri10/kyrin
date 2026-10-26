import dataclasses

import pytest

from kyrin.audio.audio_format import AudioFormat, AudioSampleFormat


def test_audio_format_stores_values() -> None:
    audio_format = AudioFormat(
        sample_rate=16000,
        channels=1,
        sample_format=AudioSampleFormat.INT16,
    )

    assert audio_format.sample_rate == 16000
    assert audio_format.channels == 1
    assert audio_format.sample_format == AudioSampleFormat.INT16


def test_audio_format_is_immutable() -> None:
    audio_format = AudioFormat(
        sample_rate=16000,
        channels=1,
        sample_format=AudioSampleFormat.INT16,
    )

    with pytest.raises(dataclasses.FrozenInstanceError):
        audio_format.sample_rate = 48000  # type: ignore[misc]


def test_audio_format_equality_is_based_on_values() -> None:
    format_a = AudioFormat(
        sample_rate=16000,
        channels=1,
        sample_format=AudioSampleFormat.INT16,
    )

    format_b = AudioFormat(
        sample_rate=16000,
        channels=1,
        sample_format=AudioSampleFormat.INT16,
    )

    assert format_a == format_b


def test_audio_format_rejects_zero_sample_rate() -> None:
    with pytest.raises(ValueError):
        AudioFormat(
            sample_rate=0,
            channels=1,
            sample_format=AudioSampleFormat.INT16,
        )


def test_audio_format_rejects_negative_sample_rate() -> None:
    with pytest.raises(ValueError):
        AudioFormat(
            sample_rate=-1,
            channels=1,
            sample_format=AudioSampleFormat.INT16,
        )


def test_audio_format_rejects_zero_channels() -> None:
    with pytest.raises(ValueError):
        AudioFormat(
            sample_rate=16000,
            channels=0,
            sample_format=AudioSampleFormat.INT16,
        )


def test_audio_format_rejects_negative_channels() -> None:
    with pytest.raises(ValueError):
        AudioFormat(
            sample_rate=16000,
            channels=-1,
            sample_format=AudioSampleFormat.INT16,
        )


def test_audio_sample_format_values() -> None:
    assert AudioSampleFormat.INT16.value == "int16"
    assert AudioSampleFormat.FLOAT32.value == "float32"


def test_audio_sample_format_bytes_per_sample() -> None:
    assert AudioSampleFormat.INT16.bytes_per_sample == 2
    assert AudioSampleFormat.FLOAT32.bytes_per_sample == 4


def test_audio_format_bytes_per_frame() -> None:
    audio_format = AudioFormat(
        sample_rate=16000,
        channels=2,
        sample_format=AudioSampleFormat.INT16,
    )

    assert audio_format.bytes_per_frame == 4
