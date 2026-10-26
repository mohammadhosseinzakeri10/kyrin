"""Verified speaker labels for supported sherpa-onnx Kokoro packages.

The binary ``voices.bin`` contains voice data, not a public name-to-ID index.
Keep labels tied to the exact official package version; unknown packages use
the numeric speaker control instead of guessing names.
"""

from pathlib import Path

# Source: https://k2-fsa.github.io/sherpa/onnx/tts/pretrained_models/kokoro.html
_V1_0_ENGLISH: tuple[tuple[int, str, str], ...] = (
    *((index, name, "American English, female") for index, name in enumerate((
        "af_alloy", "af_aoede", "af_bella", "af_heart", "af_jessica",
        "af_kore", "af_nicole", "af_nova", "af_river", "af_sarah", "af_sky",
    ))),
    *((index + 11, name, "American English, male") for index, name in enumerate((
        "am_adam", "am_echo", "am_eric", "am_fenrir", "am_liam",
        "am_michael", "am_onyx", "am_puck", "am_santa",
    ))),
    *((index + 20, name, "British English, female") for index, name in enumerate((
        "bf_alice", "bf_emma", "bf_isabella", "bf_lily",
    ))),
    *((index + 24, name, "British English, male") for index, name in enumerate((
        "bm_daniel", "bm_fable", "bm_george", "bm_lewis",
    ))),
)

_V1_0_CHINESE: tuple[tuple[int, str, str], ...] = (
    *((index + 45, name, "Mandarin Chinese, female") for index, name in enumerate((
        "zf_xiaobei", "zf_xiaoni", "zf_xiaoxiao", "zf_xiaoyi",
    ))),
    *((index + 49, name, "Mandarin Chinese, male") for index, name in enumerate((
        "zm_yunjian", "zm_yunxi", "zm_yunxia", "zm_yunyang",
    ))),
)

# Source: https://k2-fsa.github.io/sherpa/onnx/tts/all/Chinese-English/kokoro-multi-lang-v1_1.html
_V1_1_ENGLISH: tuple[tuple[int, str, str], ...] = (
    (0, "af_maple", "American English, female"),
    (1, "af_sol", "American English, female"),
    (2, "bf_vale", "British English, female"),
)


def kokoro_voice_options(folder: Path, language: str) -> tuple[tuple[str, str], ...]:
    """Return named choices for a verified package and response language."""
    primary_language = language.lower().split("-", 1)[0]
    groups = {
        "kokoro-multi-lang-v1_0": {"en": _V1_0_ENGLISH, "zh": _V1_0_CHINESE},
        "kokoro-multi-lang-v1_1": {"en": _V1_1_ENGLISH},
        "kokoro-int8-multi-lang-v1_1": {"en": _V1_1_ENGLISH},
    }
    voices = groups.get(folder.name, {}).get(primary_language, ())
    return tuple(
        (str(speaker_id), f"{name} — {description} (ID {speaker_id})")
        for speaker_id, name, description in voices
    )
