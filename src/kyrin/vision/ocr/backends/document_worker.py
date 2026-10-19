"""Isolated CPU inference for optional document models; reads a PNG from stdin."""

import importlib.machinery
import io
import json
import resource
import sys
import types
from html.parser import HTMLParser
from pathlib import Path

from PIL import Image  # type: ignore[import-not-found]

_RESULT_PREFIX = "KYRIN_DOCUMENT_OCR_RESULT:"


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


def _surya(model_path: Path, image: Image.Image) -> str:
    from transformers import pipeline  # type: ignore[import-not-found]

    reader = pipeline("image-text-to-text", model=str(model_path), device="cpu")
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "image", "image": image},
                {"type": "text", "text": "OCR this image to HTML."},
            ],
        }
    ]
    generated = reader(text=messages, max_new_tokens=1024)
    html = generated[0]["generated_text"][-1]["content"]
    parser = _PlainText()
    parser.feed(html)
    return "\n".join(parser.parts)


def _glm(model_path: Path, image: Image.Image) -> str:
    from transformers import AutoModelForMultimodalLM, AutoProcessor

    processor = AutoProcessor.from_pretrained(
        model_path, local_files_only=True, use_fast=False
    )
    model = AutoModelForMultimodalLM.from_pretrained(
        model_path, device_map="cpu", local_files_only=True
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
    output = model.generate(**inputs, max_new_tokens=1024)
    return str(
        processor.decode(
            output[0][inputs["input_ids"].shape[-1] :], skip_special_tokens=True
        )
    )


def _dots(model_path: Path, image: Image.Image) -> str:
    # The checkpoint imports flash_attn even when its CPU eager path is selected.
    # The shim fails closed if flash attention is ever actually called.
    flash_attn = types.ModuleType("flash_attn")
    flash_attn.__spec__ = importlib.machinery.ModuleSpec("flash_attn", loader=None)

    def unavailable(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("Unexpected flash attention call in CPU mode")

    flash_attn.flash_attn_varlen_func = unavailable  # type: ignore[attr-defined]
    sys.modules["flash_attn"] = flash_attn
    from qwen_vl_utils import process_vision_info  # type: ignore[import-not-found]
    from transformers import AutoConfig, AutoModelForCausalLM, AutoProcessor

    config = AutoConfig.from_pretrained(
        model_path, trust_remote_code=True, local_files_only=True
    )
    config.vision_config.attn_implementation = "eager"

    model = AutoModelForCausalLM.from_pretrained(
        model_path,
        config=config,
        attn_implementation="eager",
        torch_dtype="auto",
        device_map="cpu",
        trust_remote_code=True,
        local_files_only=True,
    )
    processor = AutoProcessor.from_pretrained(
        model_path, trust_remote_code=True, local_files_only=True
    )
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "image", "image": image},
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
        text=[prompt], images=images, videos=videos, padding=True, return_tensors="pt"
    )
    output = model.generate(**inputs, max_new_tokens=1024)
    return str(
        processor.batch_decode(
            [output[0][len(inputs.input_ids[0]) :]],
            skip_special_tokens=True,
            clean_up_tokenization_spaces=False,
        )[0]
    )


def main() -> None:
    if len(sys.argv) != 3 or sys.argv[1] not in {"surya", "glm", "dots"}:
        raise SystemExit(2)
    _memory_limit()
    Image.MAX_IMAGE_PIXELS = 20_000_000
    image = Image.open(io.BytesIO(sys.stdin.buffer.read(32 * 1024 * 1024 + 1)))
    image.load()
    image = image.convert("RGB")
    model_path = Path(sys.argv[2])
    text = {"surya": _surya, "glm": _glm, "dots": _dots}[sys.argv[1]](model_path, image)
    print(_RESULT_PREFIX + json.dumps(text, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
