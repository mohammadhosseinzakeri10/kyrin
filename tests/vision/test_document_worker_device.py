"""Document OCR device requests must preserve explicit user intent."""

from __future__ import annotations

import sys
from types import ModuleType, SimpleNamespace

import pytest

from kyrin.vision.ocr.backends import document_worker


class FakeImage:
    def __init__(
        self, width: int, height: int, box: tuple[int, int, int, int] | None = None
    ) -> None:
        self.width = width
        self.height = height
        self.box = box

    def crop(self, box: tuple[int, int, int, int]) -> FakeImage:
        return FakeImage(box[2] - box[0], box[3] - box[1], box)


def test_large_desktop_image_is_split_into_ordered_overlapping_bands() -> None:
    frames = document_worker._dots_frames(FakeImage(1853, 1048))
    assert len(frames) == 3
    assert all(frame.width * frame.height <= 800_000 for frame in frames)
    assert frames[0].box is not None and frames[0].box[1] == 0
    assert frames[-1].box is not None and frames[-1].box[3] == 1048
    assert frames[0].box[3] > frames[1].box[1]  # type: ignore[index]


def test_small_image_is_read_without_tiling() -> None:
    image = FakeImage(600, 400)
    assert document_worker._dots_frames(image) == [image]


def test_cpu_does_not_probe_cuda(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "torch", None)
    assert document_worker._resolve_device("cpu") == "cpu"


@pytest.mark.parametrize(
    ("available", "preference", "expected"),
    [
        (False, "auto", "cpu"),
        (True, "auto", "cuda:0"),
        (True, "gpu", "cuda:0"),
    ],
)
def test_auto_and_gpu_resolution(
    monkeypatch: pytest.MonkeyPatch, available: bool, preference: str, expected: str
) -> None:
    torch = ModuleType("torch")
    torch.cuda = SimpleNamespace(is_available=lambda: available)  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "torch", torch)
    assert document_worker._resolve_device(preference) == expected


def test_explicit_gpu_fails_without_cuda(monkeypatch: pytest.MonkeyPatch) -> None:
    torch = ModuleType("torch")
    torch.cuda = SimpleNamespace(is_available=lambda: False)  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "torch", torch)
    with pytest.raises(RuntimeError, match="CUDA GPU unavailable"):
        document_worker._resolve_device("gpu")
