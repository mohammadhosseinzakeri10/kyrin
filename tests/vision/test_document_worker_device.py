"""Document OCR device requests must preserve explicit user intent."""

import sys
from types import ModuleType, SimpleNamespace

import pytest

from kyrin.vision.ocr.backends import document_worker


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
