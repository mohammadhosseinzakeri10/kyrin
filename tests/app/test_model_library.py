"""Managed speech models are copied safely and classified by engine."""

from pathlib import Path

import pytest

from kyrin.app.model_library import (
    ModelLibrary,
    ModelLibraryError,
    linux_model_library_path,
    vosk_language_hint,
)
from kyrin.stt.device import ComputeDevice


def test_whisper_model_is_one_copy_in_both_device_views(tmp_path: Path) -> None:
    source = tmp_path / "ggml-small.bin"
    source.write_bytes(b"lmgg" + b"example weights")
    library = ModelLibrary(tmp_path / "installed")

    cpu = library.import_model(
        source, backend="whisper", language="en", requested_device=ComputeDevice.CPU
    )
    gpu = library.import_model(
        source, backend="whisper", language="en", requested_device=ComputeDevice.GPU
    )

    assert cpu == gpu
    assert cpu.model_id.startswith("whisper-ggml-small-")
    assert cpu.model_path.read_bytes() == source.read_bytes()
    assert cpu.devices == frozenset({ComputeDevice.CPU, ComputeDevice.GPU})
    assert library.list_models() == (cpu,)


def test_same_whisper_weights_with_another_language_are_not_copied_twice(
    tmp_path: Path,
) -> None:
    source = tmp_path / "ggml-small.bin"
    source.write_bytes(b"lmgg" + b"example weights")
    library = ModelLibrary(tmp_path / "installed")
    english = library.import_model(
        source, backend="whisper", language="en", requested_device=ComputeDevice.CPU
    )

    detected = library.import_model(
        source,
        backend="whisper",
        language="auto",
        requested_device=ComputeDevice.GPU,
    )

    assert detected == english
    assert len(library.list_models()) == 1


def test_vosk_is_cpu_only_and_gpu_import_does_not_create_library(
    tmp_path: Path,
) -> None:
    source = tmp_path / "vosk-en"
    (source / "am").mkdir(parents=True)
    (source / "conf").mkdir()
    (source / "am" / "final.mdl").write_bytes(b"acoustic model")
    (source / "conf" / "model.conf").write_text("--sample-frequency=16000")
    library = ModelLibrary(tmp_path / "installed")

    with pytest.raises(ModelLibraryError, match="selected device"):
        library.import_model(
            source, backend="vosk", language="en", requested_device=ComputeDevice.GPU
        )
    assert not library.root.exists()

    model = library.import_model(
        source, backend="vosk", language="en", requested_device=ComputeDevice.CPU
    )
    assert model.model_id.startswith("vosk-en-")
    assert model.devices == frozenset({ComputeDevice.CPU})
    assert (model.model_path / "am" / "final.mdl").read_bytes() == b"acoustic model"


def test_official_vosk_folder_name_suggests_language_without_guessing_others() -> None:
    assert vosk_language_hint(Path("vosk-model-small-fa-0.42")) == "fa"
    assert vosk_language_hint(Path("vosk-model-en-us-0.22-lgraph")) == "en"
    assert vosk_language_hint(Path("renamed-custom-model")) is None


def test_invalid_whisper_file_is_rejected_without_copy(tmp_path: Path) -> None:
    source = tmp_path / "not-a-model.bin"
    source.write_bytes(b"wrong")
    library = ModelLibrary(tmp_path / "installed")

    with pytest.raises(ModelLibraryError, match="not a whisper.cpp"):
        library.import_model(
            source, backend="whisper", language="en", requested_device=ComputeDevice.CPU
        )
    assert not library.root.exists()


def test_library_uses_user_data_directory_without_creating_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    assert linux_model_library_path() == tmp_path / "kyrin" / "models" / "stt"
    assert not (tmp_path / "kyrin").exists()


def test_incomplete_import_cleanup_preserves_installed_model(tmp_path: Path) -> None:
    source = tmp_path / "ggml-small.bin"
    source.write_bytes(b"lmgg" + b"example weights")
    library = ModelLibrary(tmp_path / "installed")
    model = library.import_model(
        source, backend="whisper", language="en", requested_device=ComputeDevice.CPU
    )
    abandoned = library.root / ".import-leftover"
    abandoned.mkdir()
    (abandoned / "partial.bin").write_bytes(b"partial")

    library.cleanup_incomplete_imports()

    assert not abandoned.exists()
    assert library.list_models() == (model,)
