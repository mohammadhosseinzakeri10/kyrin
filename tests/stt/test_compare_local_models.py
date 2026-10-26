"""Comparison memory admission and summaries must remain explicit."""

from scripts.stt.compare_local_models import (
    cpu_memory_requirement,
    gpu_memory_requirement,
    report_row,
)


def test_cpu_memory_admission_includes_checkpoint_and_headroom() -> None:
    gib = 1024**3
    assert cpu_memory_requirement(gib) == round(2.5 * gib) + 4 * gib
    assert gpu_memory_requirement(gib) == round(1.4 * gib) + 2 * gib


def test_summary_preserves_quality_and_resource_units() -> None:
    row = report_row(
        "whisper-small",
        "fa",
        {
            "files": 2,
            "cer": 0.1,
            "wer": 0.25,
            "reference_characters": 20,
            "edit_distance": 2,
            "reference_words": 8,
            "word_edit_distance": 2,
            "model_load_seconds": 1.5,
            "peak_child_rss_mib": 700.0,
            "results": [
                {"elapsed_seconds": 2.0},
                {"elapsed_seconds": 4.0},
            ],
        },
    )
    assert row["mean_elapsed_seconds"] == 3.0
    assert row["wer"] == 0.25
    assert row["peak_child_rss_mib"] == 700.0
