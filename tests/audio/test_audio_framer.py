from collections.abc import Iterator

import numpy as np
import pytest

from kyrin.audio.audio_data import AudioData
from kyrin.audio.audio_format import AudioFormat, AudioSampleFormat
from kyrin.audio.audio_framer import AudioFramer
from kyrin.audio.sample_rate_converter import SampleRateConverter

MONO_INT16 = AudioFormat(16000, 1, AudioSampleFormat.INT16)


def test_framer_preserves_audio_across_arbitrary_chunk_boundaries() -> None:
    framer = AudioFramer(MONO_INT16, frames_per_window=3)
    data = bytes(range(14))
    chunks = [
        AudioData(data[:2], MONO_INT16),
        AudioData(data[2:6], MONO_INT16),
        AudioData(data[6:], MONO_INT16),
    ]

    windows = list(framer.frame(chunks))

    assert [len(window.data) for window in windows] == [6, 6, 2]
    assert b"".join(window.data for window in windows) == data
    assert all(window.audio_format == MONO_INT16 for window in windows)


def test_framer_output_does_not_depend_on_input_chunk_sizes() -> None:
    framer = AudioFramer(MONO_INT16, frames_per_window=4)
    data = bytes(range(40))
    one_chunk = [AudioData(data, MONO_INT16)]
    split_chunks = [
        AudioData(data[:2], MONO_INT16),
        AudioData(data[2:18], MONO_INT16),
        AudioData(data[18:26], MONO_INT16),
        AudioData(data[26:], MONO_INT16),
    ]

    assert list(framer.frame(one_chunk)) == list(framer.frame(split_chunks))


def test_framer_yields_a_complete_window_before_source_ends() -> None:
    framer = AudioFramer(MONO_INT16, frames_per_window=2)

    def source() -> Iterator[AudioData]:
        yield AudioData(b"\x00\x01\x02\x03", MONO_INT16)
        raise AssertionError("framer read ahead unnecessarily")

    assert next(framer.frame(source())).data == b"\x00\x01\x02\x03"


def test_framer_keeps_channel_boundaries_and_sample_format() -> None:
    stereo_float = AudioFormat(48000, 2, AudioSampleFormat.FLOAT32)
    framer = AudioFramer(stereo_float, frames_per_window=2)
    data = bytes(range(40))
    chunks = [AudioData(data[:8], stereo_float), AudioData(data[8:], stereo_float)]

    windows = list(framer.frame(chunks))

    assert [len(window.data) for window in windows] == [16, 16, 8]
    assert b"".join(window.data for window in windows) == data
    assert all(window.audio_format == stereo_float for window in windows)


def test_framer_skips_empty_chunks_and_empty_stream() -> None:
    framer = AudioFramer(MONO_INT16, frames_per_window=2)

    assert list(framer.frame([])) == []
    assert list(framer.frame([AudioData(b"", MONO_INT16)])) == []


def test_each_frame_call_starts_with_an_empty_buffer() -> None:
    framer = AudioFramer(MONO_INT16, frames_per_window=2)
    first = AudioData(b"\x00\x01", MONO_INT16)
    second = AudioData(b"\x02\x03", MONO_INT16)

    assert list(framer.frame([first])) == [first]
    assert list(framer.frame([second])) == [second]


def test_framer_rejects_nonpositive_window_size() -> None:
    with pytest.raises(ValueError, match="frames_per_window"):
        AudioFramer(MONO_INT16, frames_per_window=0)


def test_framer_rejects_format_change_midstream() -> None:
    framer = AudioFramer(MONO_INT16, frames_per_window=2)
    other_format = AudioFormat(8000, 1, AudioSampleFormat.INT16)
    chunks = [
        AudioData(b"\x00\x01", MONO_INT16),
        AudioData(b"\x02\x03", other_format),
    ]

    with pytest.raises(ValueError, match="format changed"):
        list(framer.frame(chunks))


def test_framer_accepts_sample_rate_converter_output() -> None:
    source_format = AudioFormat(48000, 1, AudioSampleFormat.INT16)
    converter = SampleRateConverter(source_format, target_sample_rate=16000)
    framer = AudioFramer(converter.output_format, frames_per_window=320)
    signal = np.zeros(48000, dtype=np.int16)
    source_chunks = (
        AudioData(signal[start : start + 1024].tobytes(), source_format)
        for start in range(0, len(signal), 1024)
    )

    windows = list(framer.frame(converter.convert(source_chunks)))

    assert len(windows) == 50
    assert all(len(window.data) == 640 for window in windows)
