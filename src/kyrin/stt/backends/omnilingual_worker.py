"""Python 3.12 entry point for the isolated Omnilingual ASR runtime.

This file deliberately imports no KYRIN modules: the main application uses
Python 3.14 while the upstream inference package currently requires <3.14.
"""

import base64
import contextlib
import io
import json
import os
import re
import sys
import tempfile
import wave
from pathlib import Path

_NAME = re.compile(r"omniASR_(CTC|LLM)_(300M|1B|3B)_v2\Z")


def _send(**message: object) -> None:
    sys.stdout.write(json.dumps(message, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def _cards(folder: Path, directory: Path) -> str:
    match = _NAME.fullmatch(folder.name)
    if match is None:
        raise ValueError("unsupported Omnilingual ASR model folder")
    family, size = match.groups()
    checkpoint = folder / f"omniASR-{family}-{size}-v2.pt"
    tokenizer = folder / "omniASR_tokenizer_written_v2.model"
    if not checkpoint.is_file() or not tokenizer.is_file():
        raise FileNotFoundError("local model checkpoint or tokenizer is missing")
    name = "kyrin_" + folder.name
    tokenizer_name = "kyrin_omniASR_tokenizer_written_v2"
    model_family = "wav2vec2_asr" if family == "CTC" else "wav2vec2_llama"
    (directory / "kyrin_omnilingual.yaml").write_text(
        "\n".join(
            (
                f"name: {tokenizer_name}",
                "tokenizer_family: char_tokenizer",
                f"tokenizer: {json.dumps(tokenizer.resolve().as_uri())}",
                "---",
                f"name: {name}",
                f"model_family: {model_family}",
                f"model_arch: {size.lower()}_v2",
                f"checkpoint: {json.dumps(checkpoint.resolve().as_uri())}",
                f"tokenizer_ref: {tokenizer_name}",
                "",
            )
        ),
        encoding="utf-8",
    )
    return name


def _wav(pcm: bytes) -> bytes:
    with io.BytesIO() as output:
        with wave.open(output, "wb") as stream:
            stream.setnchannels(1)
            stream.setsampwidth(2)
            stream.setframerate(16_000)
            stream.writeframes(pcm)
        return output.getvalue()


def main() -> int:
    folder = Path(sys.argv[1]).resolve()
    requested_device = sys.argv[2]
    with tempfile.TemporaryDirectory(prefix="kyrin-omni-cards-") as temporary:
        card_name = _cards(folder, Path(temporary))
        os.environ["FAIRSEQ2_USER_ASSET_DIR"] = temporary
        with contextlib.redirect_stdout(sys.stderr):
            import torch  # type: ignore[import-not-found]
            from omnilingual_asr.models.inference.pipeline import (  # type: ignore[import-not-found]
                ASRInferencePipeline,
            )

            available = torch.cuda.is_available()
            if requested_device == "gpu" and not available:
                raise RuntimeError("CUDA is unavailable for Omnilingual ASR")
            device = "cuda" if requested_device != "cpu" and available else "cpu"
            dtype = torch.bfloat16 if device == "cuda" else torch.float32
            pipeline = ASRInferencePipeline(
                model_card=card_name, device=device, dtype=dtype
            )
        _send(status="ready", device="gpu" if device == "cuda" else "cpu")
        for line in sys.stdin:
            try:
                request = json.loads(line)
                pcm = base64.b64decode(request["pcm"], validate=True)
                language = str(request["language"])
                if len(pcm) > 30 * 16_000 * 2 or len(pcm) % 2:
                    raise ValueError("audio must be 16 kHz mono INT16, at most 30 s")
                lang_id = {
                    "en": "eng_Latn",
                    "fa": "fas_Arab",
                    "de": "deu_Latn",
                    "fr": "fra_Latn",
                    "auto": None,
                }.get(language, language)
                if lang_id is not None and "_" not in lang_id:
                    raise ValueError(
                        "Use auto, en, fa, de, fr, or an Omnilingual language ID"
                    )
                with contextlib.redirect_stdout(sys.stderr):
                    result = pipeline.transcribe(
                        [_wav(pcm)],
                        lang=[lang_id] if lang_id else None,
                        batch_size=1,
                    )
                _send(status="ok", text=result[0])
            except (KeyError, ValueError, RuntimeError, OSError) as error:
                _send(status="error", error=str(error))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ImportError, ValueError, RuntimeError, OSError) as error:
        _send(status="error", error=str(error))
        raise SystemExit(1) from error
