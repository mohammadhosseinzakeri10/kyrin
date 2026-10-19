"""Offline PaddleOCR-VL spotting worker with real boxes and unknown confidence."""

import io
import json
import os
import resource
import sys
from pathlib import Path


def _limit_address_space() -> None:
    """Keep a document model from exhausting an interactive desktop."""
    try:
        physical = os.sysconf("SC_PHYS_PAGES") * os.sysconf("SC_PAGE_SIZE")
        soft, hard = resource.getrlimit(resource.RLIMIT_AS)
        limit = min(16 * 1024**3, int(physical * 0.6))
        if soft != resource.RLIM_INFINITY:
            limit = min(limit, soft)
        if hard != resource.RLIM_INFINITY:
            limit = min(limit, hard)
        resource.setrlimit(resource.RLIMIT_AS, (limit, hard))
    except (OSError, ValueError):
        return


def main() -> int:
    if len(sys.argv) != 2:
        return 2
    model_path = Path(sys.argv[1])
    image_bytes = sys.stdin.buffer.read(32 * 1024 * 1024 + 1)
    if len(image_bytes) > 32 * 1024 * 1024:
        return 2

    _limit_address_space()
    import numpy as np
    from paddleocr import PaddleOCRVL  # type: ignore[import-not-found]
    from PIL import Image  # type: ignore[import-not-found]

    image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    width, height = image.size
    pipeline = PaddleOCRVL(
        pipeline_version="v1.6",
        vl_rec_model_dir=str(model_path),
        use_layout_detection=False,
        use_doc_orientation_classify=False,
        use_doc_unwarping=False,
        device="cpu",
    )
    spans = []
    for result in pipeline.predict(np.asarray(image), prompt_label="spotting"):
        spotting = result.json["res"].get("spotting_res") or {}
        for text, polygon in zip(
            spotting.get("rec_texts", []),
            spotting.get("rec_polys", []),
            strict=True,
        ):
            if not text.strip() or len(polygon) != 4:
                continue
            left = max(0, round(min(point[0] for point in polygon)))
            top = max(0, round(min(point[1] for point in polygon)))
            right = min(width, round(max(point[0] for point in polygon)))
            bottom = min(height, round(max(point[1] for point in polygon)))
            if right <= left or bottom <= top:
                continue
            spans.append(
                {
                    "text": str(text),
                    "box": [left, top, right, bottom],
                    "confidence": None,
                }
            )
    print("KYRIN_OCR_RESULT:" + json.dumps(spans, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
