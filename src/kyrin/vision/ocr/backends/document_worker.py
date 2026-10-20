"""Isolated CPU/CUDA inference for optional document models; reads PNG from stdin."""

from __future__ import annotations

import importlib.machinery
import io
import json
import math
import resource
import sys
import types
from html.parser import HTMLParser
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from PIL import Image  # type: ignore[import-not-found]

_RESULT_PREFIX = "KYRIN_DOCUMENT_OCR_RESULT:"
_DOTS_MAX_FRAME_PIXELS = 800_000
_DOTS_BAND_OVERLAP = 32


class _PlainText(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        if data.strip():
            self.parts.append(data.strip())


def _memory_limit() -> None:
    # This machine has no swap. A single experimental model must not exhaust it.
    limit = 18_000_000_000
    resource.setrlimit(resource.RLIMIT_AS, (limit, limit))


def _resolve_device(preference: str) -> str:
    if preference == "cpu":
        return "cpu"
    import torch  # type: ignore[import-not-found]

    if torch.cuda.is_available():
        return "cuda:0"
    if preference == "gpu":
        raise RuntimeError("CUDA GPU unavailable")
    return "cpu"


def _surya(model_path: Path, image: Image.Image, device: str) -> str:
    from transformers import pipeline  # type: ignore[import-not-found]

    reader = pipeline("image-text-to-text", model=str(model_path), device=device)

    def recognize(frame: Image.Image) -> str:
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "image", "image": frame},
                    {"type": "text", "text": "OCR this image to HTML."},
                ],
            }
        ]
        generated = reader(text=messages, max_new_tokens=1024)
        html = generated[0]["generated_text"][-1]["content"]
        parser = _PlainText()
        parser.feed(html)
        return "\n".join(parser.parts)

    text = recognize(image)
    if text.strip() or image.width < 800 or image.height < 400:
        return text
    # Full desktop UI frames can produce empty page HTML even when the main
    # panel contains readable text. Retry once without the left navigation.
    main_panel = image.crop((int(image.width * 0.15), 0, image.width, image.height))
    return recognize(main_panel)


def _glm(model_path: Path, image: Image.Image, device: str) -> str:
    from transformers import AutoModelForMultimodalLM, AutoProcessor

    processor = AutoProcessor.from_pretrained(
        model_path, local_files_only=True, use_fast=False
    )
    model = AutoModelForMultimodalLM.from_pretrained(
        model_path, device_map=device, local_files_only=True
    )
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "image", "image": image},
                {"type": "text", "text": "Text Recognition:"},
            ],
        }
    ]
    inputs = processor.apply_chat_template(
        messages,
        add_generation_prompt=True,
        tokenize=True,
        return_dict=True,
        return_tensors="pt",
    )
    inputs = inputs.to(device)
    output = model.generate(**inputs, max_new_tokens=1024)
    return str(
        processor.decode(
            output[0][inputs["input_ids"].shape[-1] :], skip_special_tokens=True
        )
    )


def _dots_frames(image: Image.Image) -> list[Image.Image]:
    """Keep desktop text at its original scale while bounding vision memory."""
    if image.width * image.height <= _DOTS_MAX_FRAME_PIXELS:
        return [image]
    max_height = max(64, _DOTS_MAX_FRAME_PIXELS // image.width)
    band_count = math.ceil(image.height / max(1, max_height - _DOTS_BAND_OVERLAP))
    core_height = math.ceil(image.height / band_count)
    frames = []
    for index in range(band_count):
        top = max(0, index * core_height - _DOTS_BAND_OVERLAP // 2)
        bottom = min(image.height, (index + 1) * core_height + _DOTS_BAND_OVERLAP // 2)
        frames.append(image.crop((0, top, image.width, bottom)))
    return frames


def _dots(model_path: Path, image: Image.Image, device: str) -> str:
    # The checkpoint imports flash_attn even when a different path is selected.
    # The shim fails closed if flash attention is ever actually called.
    flash_attn = types.ModuleType("flash_attn")
    flash_attn.__spec__ = importlib.machinery.ModuleSpec("flash_attn", loader=None)

    def unavailable(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("Unexpected flash attention call in eager mode")

    flash_attn.flash_attn_varlen_func = unavailable  # type: ignore[attr-defined]
    sys.modules["flash_attn"] = flash_attn
    from qwen_vl_utils import process_vision_info  # type: ignore[import-not-found]
    from transformers import AutoConfig, AutoModelForCausalLM, AutoProcessor

    config = AutoConfig.from_pretrained(
        model_path, trust_remote_code=True, local_files_only=True
    )
    # Eager vision attention materializes an image-token square matrix and
    # exhausts 16 GB GPUs on ordinary desktop screenshots. The checkpoint's
    # SDPA implementation avoids that large floating-point attention matrix.
    attention = "sdpa" if device.startswith("cuda") else "eager"
    config.vision_config.attn_implementation = attention

    model = AutoModelForCausalLM.from_pretrained(
        model_path,
        config=config,
        attn_implementation=attention,
        torch_dtype="auto",
        device_map=device,
        trust_remote_code=True,
        local_files_only=True,
    )
    processor = AutoProcessor.from_pretrained(
        model_path, trust_remote_code=True, local_files_only=True
    )

    def recognize(frame: Image.Image) -> str:
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "image", "image": frame},
                    {
                        "type": "text",
                        "text": (
                            "Extract all visible text from this image. "
                            "Return only the text."
                        ),
                    },
                ],
            }
        ]
        prompt = processor.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True
        )
        images, videos = process_vision_info(messages)
        inputs = processor(
            text=[prompt],
            images=images,
            videos=videos,
            padding=True,
            return_tensors="pt",
        ).to(device)
        output = model.generate(**inputs, max_new_tokens=1024)
        return str(
            processor.batch_decode(
                [output[0][len(inputs.input_ids[0]) :]],
                skip_special_tokens=True,
                clean_up_tokenization_spaces=False,
            )[0]
        )

    frames = _dots_frames(image) if device.startswith("cuda") else [image]
    return "\n".join(text for frame in frames if (text := recognize(frame)).strip())


def main() -> None:
    from PIL import Image

    if (
        len(sys.argv) != 4
        or sys.argv[1] not in {"surya", "glm", "dots"}
        or sys.argv[3] not in {"auto", "cpu", "gpu"}
    ):
        raise SystemExit(2)
    try:
        device = _resolve_device(sys.argv[3])
    except RuntimeError as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(20) from error
    if device == "cpu":
        _memory_limit()
    Image.MAX_IMAGE_PIXELS = 20_000_000
    image = Image.open(io.BytesIO(sys.stdin.buffer.read(32 * 1024 * 1024 + 1)))
    image.load()
    image = image.convert("RGB")
    model_path = Path(sys.argv[2])
    text = {"surya": _surya, "glm": _glm, "dots": _dots}[sys.argv[1]](
        model_path, image, device
    )
    print(
        _RESULT_PREFIX
        + json.dumps(
            {"text": text, "device": "gpu" if device.startswith("cuda") else "cpu"},
            ensure_ascii=False,
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
