"""TTS package families built into the desktop installation."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class TtsFamily:
    """One supported local package format and its user-facing name."""

    key: str
    label: str
    folder_prefixes: tuple[str, ...]
    sherpa_config: str
    needs_voices: bool = False
    needs_lexicon: bool = False
    max_voice: int = 255


TTS_FAMILIES: tuple[TtsFamily, ...] = (
    TtsFamily(
        "kitten",
        "Kitten (local)",
        ("kitten-",),
        "OfflineTtsKittenModelConfig",
        needs_voices=True,
        max_voice=7,
    ),
    TtsFamily(
        "kokoro",
        "Kokoro (local)",
        ("kokoro-",),
        "OfflineTtsKokoroModelConfig",
        needs_voices=True,
        needs_lexicon=True,
    ),
    TtsFamily(
        "vits", "Piper / VITS (local)", ("vits-", "piper-"), "OfflineTtsVitsModelConfig"
    ),
)

TTS_FAMILY_KEYS = frozenset(family.key for family in TTS_FAMILIES)
TTS_FAMILY_BY_KEY = {family.key: family for family in TTS_FAMILIES}
