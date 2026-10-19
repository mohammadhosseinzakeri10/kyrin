"""One-shot PaddleOCR worker; stdout contains only a framed JSON result."""

import io
import json
import sys
from pathlib import Path


def main() -> int:
    if len(sys.argv) != 4:
        return 2
    model_path = Path(sys.argv[1])
    det_name, rec_name = sys.argv[2:4]
    import numpy as np
    from paddleocr import PaddleOCR  # type: ignore[import-not-found]
    from PIL import Image  # type: ignore[import-not-found]

    image_bytes = sys.stdin.buffer.read(32 * 1024 * 1024 + 1)
    if len(image_bytes) > 32 * 1024 * 1024:
        return 2
    image = Image.open(io.BytesIO(image_bytes))
    image.load()
    pipeline = PaddleOCR(
        text_detection_model_name=det_name,
        text_detection_model_dir=str(model_path / "det"),
        text_recognition_model_name=rec_name,
        text_recognition_model_dir=str(model_path / "rec"),
        use_doc_orientation_classify=False,
        use_doc_unwarping=False,
        use_textline_orientation=False,
        device="cpu",
        enable_mkldnn=False,
    )
    spans = []
    for result in pipeline.predict(np.asarray(image.convert("RGB"))):
        data = result.json["res"]
        for text, box, confidence in zip(
            data["rec_texts"], data["rec_boxes"], data["rec_scores"], strict=True
        ):
            spans.append(
                {
                    "text": str(text),
                    "box": [int(value) for value in box],
                    "confidence": float(confidence),
                }
            )
    print("KYRIN_OCR_RESULT:" + json.dumps(spans, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
