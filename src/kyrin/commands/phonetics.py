"""Optional existing eSpeak text-to-IPA; no synthesis, model or download."""

import atexit
import ctypes
import ctypes.util
import re
from functools import lru_cache
from threading import Lock

_LOCK = Lock()
_LIBRARY: ctypes.CDLL | None = None
_ATTEMPTED = False


def _initialize() -> ctypes.CDLL | None:
    global _LIBRARY, _ATTEMPTED
    if _ATTEMPTED:
        return _LIBRARY
    _ATTEMPTED = True
    library = ctypes.util.find_library("espeak-ng")
    if library is None:
        return None
    try:
        lib = ctypes.CDLL(library)
    except OSError:
        return None
    lib.espeak_Initialize.argtypes = [
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_int,
    ]
    lib.espeak_Initialize.restype = ctypes.c_int
    lib.espeak_SetVoiceByName.argtypes = [ctypes.c_char_p]
    lib.espeak_SetVoiceByName.restype = ctypes.c_int
    lib.espeak_TextToPhonemes.argtypes = [
        ctypes.POINTER(ctypes.c_void_p),
        ctypes.c_int,
        ctypes.c_int,
    ]
    lib.espeak_TextToPhonemes.restype = ctypes.c_char_p
    lib.espeak_Terminate.argtypes = []
    lib.espeak_Terminate.restype = ctypes.c_int
    if lib.espeak_Initialize(1, 0, None, 0) <= 0:
        return None
    _LIBRARY = lib
    atexit.register(lib.espeak_Terminate)
    return lib


@lru_cache(maxsize=256)
def english_phonemes(text: str) -> str | None:
    """Only short control spans are cached; free payloads are never passed here."""
    if not text.strip() or len(text) > 64:
        return None
    # eSpeak voice state is process-global. Serialize voice selection and use.
    with _LOCK:
        lib = _initialize()
        if lib is None or lib.espeak_SetVoiceByName(b"en-us") != 0:
            return None
        buffer = ctypes.create_string_buffer(text.encode("utf-8"))
        pointer = ctypes.cast(buffer, ctypes.c_void_p)
        parts = []
        for _ in range(8):
            if not pointer.value:
                break
            previous = pointer.value
            output = lib.espeak_TextToPhonemes(ctypes.byref(pointer), 1, 2)
            if output:
                parts.append(output.decode("utf-8"))
            if pointer.value == previous:
                return None
        if pointer.value:
            return None
        return re.sub(r"[\sˈˌ_]+", "", "".join(parts)) or None


def phonetic_similarity(left: str, right: str) -> float:
    """Experimental weighted IPA edit similarity, not an acoustic probability.

    Vowel variants and English rhotic variation are cheaper retrieval edits.
    The semantic/role and destination checks remain mandatory after retrieval.
    """
    vowels = r"[aeiouæɑɒʌəɚɝɜɛɪʊɔːˑ]+"
    first = re.findall(vowels + r"|.", left)
    second = re.findall(vowels + r"|.", right)
    if not first or not second:
        return 0.0

    def insertion(token: str) -> float:
        return 0.5 if token in {"ɹ", "r"} else 1.0

    def substitution(a: str, b: str) -> float:
        if a == b:
            return 0.0
        if re.fullmatch(vowels, a) and re.fullmatch(vowels, b):
            return 0.35
        if {a, b} in ({"s", "z"}, {"ɹ", "r"}):
            return 0.35
        return 1.0

    previous = [0.0]
    for token in second:
        previous.append(previous[-1] + insertion(token))
    for token in first:
        current = [previous[0] + insertion(token)]
        for index, other in enumerate(second, 1):
            current.append(
                min(
                    previous[index] + insertion(token),
                    current[index - 1] + insertion(other),
                    previous[index - 1] + substitution(token, other),
                )
            )
        previous = current
    return max(0.0, 1 - previous[-1] / max(len(first), len(second)))
