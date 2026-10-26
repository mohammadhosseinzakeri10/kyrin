from collections.abc import Iterator

import numpy as np
import pytest

from kyrin.audio.audio_data import AudioData
from kyrin.audio.audio_format import AudioFormat, AudioSampleFormat
from kyrin.audio.sample_rate_converter import SampleRateConverter


def make_format(
    sample_rate: int = 48000,
    channels: int = 1,
    sample_format: AudioSampleFormat = AudioSampleFormat.INT16,
) -> AudioFormat:
    return AudioFormat(sample_rate, channels, sample_format)


def make_tone(sample_rate: int, frequency: int) -> np.ndarray:
    time = np.arange(sample_rate) / sample_rate
    return (20000 * np.sin(2 * np.pi * frequency * time)).astype(np.int16)


@pytest.mark.parametrize("input_rate", [8000, 44100, 48000])
def test_resampling_preserves_duration_across_chunk_boundaries(input_rate: int) -> None:
    input_format = make_format(input_rate)
    converter = SampleRateConverter(input_format, target_sample_rate=16000)
    tone = make_tone(input_rate, frequency=440)

    whole = list(converter.convert([AudioData(tone.tobytes(), input_format)]))
    chunked_input = (
        AudioData(tone[start : start + 777].tobytes(), input_format)
        for start in range(0, len(tone), 777)
    )
    chunked = list(converter.convert(chunked_input))

    whole_samples = np.frombuffer(b"".join(chunk.data for chunk in whole), np.int16)
    chunked_samples = np.frombuffer(b"".join(chunk.data for chunk in chunked), np.int16)

    assert len(whole_samples) == 16000
    assert len(chunked_samples) == 16000
    difference = np.abs(
        whole_samples.astype(np.int32) - chunked_samples.astype(np.int32)
    )
    assert np.max(difference) <= 4
    assert all(chunk.audio_format == converter.output_format for chunk in chunked)


def test_resampling_filters_frequencies_above_output_nyquist() -> None:
    input_format = make_format()
    converter = SampleRateConverter(input_format, target_sample_rate=16000)

    def output_rms(frequency: int) -> float:
        tone = make_tone(input_format.sample_rate, frequency)
        chunks = converter.convert([AudioData(tone.tobytes(), input_format)])
        samples = np.frombuffer(b"".join(chunk.data for chunk in chunks), np.int16)
        middle = samples[200:-200].astype(np.float64)
        return float(np.sqrt(np.mean(middle**2)))

    assert output_rms(10000) < output_rms(440) * 0.01


def test_converter_yields_before_source_stream_ends() -> None:
    input_format = make_format()
    converter = SampleRateConverter(input_format, target_sample_rate=16000)
    chunks_read = 0

    def input_chunks() -> Iterator[AudioData]:
        nonlocal chunks_read
        for _ in range(100):
            chunks_read += 1
            yield AudioData(np.zeros(1024, dtype=np.int16).tobytes(), input_format)
        raise AssertionError("converter consumed the complete input")

    first_output = next(converter.convert(input_chunks()))

    assert first_output.data
    assert chunks_read < 100


def test_equal_sample_rates_pass_through_audio() -> None:
    input_format = make_format(16000)
    converter = SampleRateConverter(input_format, target_sample_rate=16000)
    input_chunk = AudioData(b"\x00\x01\x02\x03", input_format)

    assert list(converter.convert([input_chunk])) == [input_chunk]


def test_empty_input_produces_no_audio() -> None:
    converter = SampleRateConverter(make_format(), target_sample_rate=16000)

    assert list(converter.convert([])) == []


@pytest.mark.parametrize(
    "input_format",
    [make_format(channels=2), make_format(sample_format=AudioSampleFormat.FLOAT32)],
)
def test_converter_rejects_unsupported_input_format(input_format: AudioFormat) -> None:
    with pytest.raises(ValueError, match="mono INT16"):
        SampleRateConverter(input_format, target_sample_rate=16000)


def test_converter_rejects_nonpositive_target_rate() -> None:
    with pytest.raises(ValueError, match="target_sample_rate"):
        SampleRateConverter(make_format(), target_sample_rate=0)


def test_converter_rejects_format_change_midstream() -> None:
    input_format = make_format()
    converter = SampleRateConverter(input_format, target_sample_rate=16000)
    chunks = [
        AudioData(b"\x00\x00", input_format),
        AudioData(b"\x00\x00", make_format(44100)),
    ]

    with pytest.raises(ValueError, match="format changed"):
        list(converter.convert(chunks))
