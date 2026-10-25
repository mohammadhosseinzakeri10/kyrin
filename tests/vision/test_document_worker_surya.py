"""Surya retries the main panel when full-window UI OCR returns nothing."""

from __future__ import annotations

import sys
from pathlib import Path
from types import ModuleType

import pytest

from kyrin.vision.ocr.backends import document_worker


class FakeImage:
    def __init__(self, width: int, height: int) -> None:
        self.width = width
        self.height = height
        self.crops: list[tuple[int, int, int, int]] = []

    def crop(self, box: tuple[int, int, int, int]) -> FakeImage:
        self.crops.append(box)
        return FakeImage(box[2] - box[0], box[3] - box[1])


def test_surya_retries_wide_ui_on_empty_full_window(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    frames: list[FakeImage] = []

    def reader(
        *, text: list[dict[str, object]], max_new_tokens: int
    ) -> list[dict[str, object]]:
        assert max_new_tokens == 1024
        frame = text[0]["content"][0]["image"]  # type: ignore[index]
        frames.append(frame)
        html = "" if len(frames) == 1 else "<div>Main panel text</div>"
        return [{"generated_text": [{"content": html}]}]

    transformers = ModuleType("transformers")
    transformers.pipeline = lambda *_args, **_kwargs: reader  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "transformers", transformers)
    image = FakeImage(1200, 820)

    assert document_worker._surya(Path("/fake"), image, "cpu") == "Main panel text"
    assert image.crops == [(180, 0, 1200, 820)]
    assert len(frames) == 2


def test_surya_skips_retry_when_full_window_has_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def reader(*, text: object, max_new_tokens: int) -> list[dict[str, object]]:
        assert text is not None and max_new_tokens == 1024
        return [{"generated_text": [{"content": "<p>Already read</p>"}]}]

    transformers = ModuleType("transformers")
    transformers.pipeline = lambda *_args, **_kwargs: reader  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "transformers", transformers)
    image = FakeImage(1200, 820)

    assert document_worker._surya(Path("/fake"), image, "cpu") == "Already read"
    assert not image.crops
