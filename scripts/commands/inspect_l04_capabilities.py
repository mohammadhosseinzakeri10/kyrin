"""Inspect project-local assets and phonetic feasibility without audio capture.

The optional eSpeak call converts fixed public text to phonemes in retrieval
mode. It never synthesizes or plays audio, accesses private text or downloads.
"""

import argparse
import ctypes
import ctypes.util
import hashlib
import importlib.util
import json
from pathlib import Path

from kyrin.commands.ollama_models import ollama_model_stores

ROOT = Path(__file__).resolve().parents[2]


def phonetic_probe() -> dict[str, object]:
    library = ctypes.util.find_library("espeak-ng")
    if library is None:
        return {"available": False, "reason": "shared_library_not_found"}
    lib = ctypes.CDLL(library)
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
    # AUDIO_OUTPUT_RETRIEVAL=1; TextToPhonemes UTF8=1, IPA=2.
    sample_rate = lib.espeak_Initialize(1, 0, None, 0)
    if sample_rate <= 0:
        return {"available": False, "reason": "initialization_failed"}
    examples: dict[str, dict[str, str | None]] = {}
    try:
        for voice, words in (
            (
                "en-us",
                (
                    "scroll",
                    "school",
                    "screwl",
                    "open",
                    "oh pen",
                    "close",
                    "clothes",
                    "minimize",
                    "mini mice",
                ),
            ),
            ("fa", ("اسکرول", "مدرسه")),
        ):
            if lib.espeak_SetVoiceByName(voice.encode()) != 0:
                examples[voice] = {"error": "voice_unavailable"}
                continue
            examples[voice] = {}
            for word in words:
                buffer = ctypes.create_string_buffer(word.encode("utf-8"))
                pointer = ctypes.cast(buffer, ctypes.c_void_p)
                output = lib.espeak_TextToPhonemes(ctypes.byref(pointer), 1, 2)
                examples[voice][word] = output.decode("utf-8") if output else None
    finally:
        lib.espeak_Terminate()
    return {
        "available": True,
        "library": library,
        "mode": "text_to_IPA_only",
        "examples": examples,
        "accent_accuracy_measured": False,
    }


def inventory() -> dict[str, object]:
    stores = ollama_model_stores(
        ROOT / "models/local/by-model/command-understanding/ollama"
    )
    models: list[dict[str, object]] = []
    for tag, store in stores.items():
        repository, variant = tag.split(":", 1)
        manifest = store / "manifests/registry.ollama.ai/library" / repository / variant
        document = json.loads(manifest.read_text())
        models.append(
            {
                "tag": tag,
                "store": str(store),
                "manifest_sha256": hashlib.sha256(manifest.read_bytes()).hexdigest(),
                "referenced_bytes": sum(
                    layer["size"] for layer in [document["config"], *document["layers"]]
                ),
                "blobs_present": True,
                "weight_hashes_recomputed": False,
            }
        )
    stt = ROOT / "models/local/by-model/stt"
    return {
        "schema": 1,
        "command_models": models,
        "stt_assets": [
            str(p.relative_to(ROOT))
            for p in sorted(stt.rglob("*"))
            if p.is_file()
            and (
                p.name
                in {"ggml-small.bin", "ggml-large-v3-turbo-q5_0.bin", "final.mdl"}
                or p.name.startswith("omniASR-")
                and p.suffix == ".pt"
            )
        ],
        "python_packages_in_probe_runtime": {
            package: importlib.util.find_spec(package) is not None
            for package in ("vosk", "phonemizer", "cmudict", "pronouncing", "g2p_en")
        },
        "phonetic_probe": phonetic_probe(),
        "live_hardware_or_asr_accuracy_test": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("output already exists")
    result = inventory()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as output:
        json.dump(result, output, ensure_ascii=False, indent=2)
        output.write("\n")
    print(f"Capability report: {args.output}")


if __name__ == "__main__":
    main()
