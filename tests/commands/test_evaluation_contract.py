"""E03 rejects incompatible plans and keeps provenance/unknowns explicit."""

import copy
import json
import subprocess
from pathlib import Path
from typing import Any, cast
from unittest.mock import patch

import pytest

from scripts.commands.evaluation_contract import (
    DEFAULT_PLAN,
    ROOT,
    environment_snapshot,
    file_hash,
    fingerprint,
    group_key,
    read_json,
    source_snapshot,
    validate_plan,
    validate_profile,
    write_new,
)


@pytest.fixture
def plan() -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(DEFAULT_PLAN.read_text()))


def test_portable_plan_binds_real_inputs_and_preserves_unknowns(
    plan: dict[str, Any],
) -> None:
    assert validate_plan(plan) == plan
    assert plan["profiles"][0]["hardware"]["vram_bytes"] is None
    assert plan["profiles"][0]["model"]["artifact_sha256"] is None
    assert plan["protocol"]["profile_order"] == ["gpu-qwen9b", "cpu-qwen4b"]
    assert plan["protocol"]["min_percentile_samples"] == 20


@pytest.mark.parametrize(
    ("section", "field", "value"),
    [
        (None, "schema_version", True),
        (None, "schema_version", 2),
        (None, "extra", "unknown"),
        ("memory", "unit", "MiB"),
        ("memory", "interval_ms", 0),
        ("memory", "interval_ms", True),
        ("memory", "extra", 1),
        ("protocol", "min_percentile_samples", 19),
        ("protocol", "max_seconds", -1),
        ("protocol", "reuse", "cached"),
        ("protocol", "executor", "desktop"),
        ("corpus", "sha256", "0" * 64),
        ("corpus", "references_sha256", "0" * 64),
        ("corpus", "case_ids", ["missing"]),
        ("corpus", "path", "../private"),
    ],
)
def test_rejects_invalid_plan(
    plan: dict[str, Any],
    section: str | None,
    field: str,
    value: object,
) -> None:
    target = plan if section is None else plan[section]
    target[field] = value
    with pytest.raises(ValueError):
        validate_plan(plan)


@pytest.mark.parametrize(
    ("section", "field", "value"),
    [
        (None, "context_tokens", 800),
        (None, "output_tokens", True),
        (None, "expected_placements", ["gpu"]),
        (None, "deadline_seconds", 120),
        (None, "confirmation_tokens", 65),
        ("hardware", "vram_bytes", -1),
        ("hardware", "ram_bytes", False),
        ("generation", "temperature", float("nan")),
        ("generation", "temperature", True),
        ("generation", "cleanup_keep_alive", False),
        ("generation", "keep_alive", "5m"),
        ("generation", "truncate", True),
        ("model", "artifact_sha256", "bad"),
    ],
)
def test_rejects_invalid_profile(
    plan: dict[str, Any],
    section: str | None,
    field: str,
    value: object,
) -> None:
    profile = plan["profiles"][0]
    target = profile if section is None else profile[section]
    target[field] = value
    with pytest.raises(ValueError):
        validate_profile(profile)


def test_ready_requires_resolved_model_and_active_components(
    plan: dict[str, Any],
) -> None:
    profile = plan["profiles"][-1]
    profile["status"] = "ready"
    with pytest.raises(ValueError, match="identity"):
        validate_profile(profile)
    profile["model"].update(artifact_sha256="a" * 64, runtime_version="0.31.1")
    with pytest.raises(ValueError, match="component"):
        validate_profile(profile)
    for component in ("stt", "tts"):
        profile["composition"][component]["artifact"] = "test-artifact-sha256"
    assert validate_profile(profile) == profile


def test_cpu_and_gpu_placement_policy_use_existing_contract(
    plan: dict[str, Any],
) -> None:
    cpu = plan["profiles"][1]
    cpu["expected_placements"] = ["unknown"]
    with pytest.raises(ValueError, match="policy"):
        validate_profile(cpu)
    gpu = plan["profiles"][0]
    assert validate_profile(gpu)["expected_placements"] == [
        "gpu",
        "mixed",
        "gpu_participation",
    ]


def binding(plan: dict[str, Any]) -> dict[str, object]:
    return {
        "schema_version": 1,
        "tool_version": "1",
        "plan_sha256": fingerprint(plan),
        "profile_sha256": fingerprint(plan["profiles"][0]),
        "source_sha256": "a" * 64,
        "environment_sha256": "b" * 64,
        "corpus_sha256": plan["corpus"]["sha256"],
        "references_sha256": plan["corpus"]["references_sha256"],
        "case_order": plan["corpus"]["case_ids"],
        "level": "adapter",
        "temperature": "unknown",
        "service_state": "started",
        "placement": "gpu",
        "reuse": "fresh",
    }


@pytest.mark.parametrize("field", ["model", "context_tokens", "requested_device"])
def test_profile_change_cannot_silently_pool_samples(
    plan: dict[str, Any],
    field: str,
) -> None:
    original = binding(plan)
    changed = copy.deepcopy(plan["profiles"][0])
    changed[field] = {"tag": "other"} if field == "model" else "changed"
    modified = dict(original, profile_sha256=fingerprint(changed))
    assert group_key(original) != group_key(modified)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("source_sha256", "c" * 64),
        ("environment_sha256", "c" * 64),
        ("temperature", "cold"),
        ("temperature", "warm"),
        ("placement", "mixed"),
        ("reuse", "resumed"),
        ("service_state", "existing"),
        ("level", "product_text"),
    ],
)
def test_conditions_and_snapshot_are_separate_groups(
    plan: dict[str, Any],
    field: str,
    value: object,
) -> None:
    original = binding(plan)
    modified = dict(original)
    modified[field] = value
    assert group_key(original) != group_key(modified)
    assert group_key(original) == group_key(dict(reversed(list(original.items()))))


def test_order_schema_and_unknown_metadata_are_validated(plan: dict[str, Any]) -> None:
    original = binding(plan)
    assert group_key(original) != group_key(
        dict(original, case_order=list(reversed(plan["corpus"]["case_ids"])))
    )
    for modified in (dict(original, schema_version=2), dict(original, extra=True)):
        with pytest.raises(ValueError):
            group_key(modified)


def test_source_identity_includes_uncommitted_untracked_and_deleted_files(
    tmp_path: Path,
) -> None:
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(tmp_path),
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.invalid",
            "commit",
            "-qm",
            "initial",
            "--allow-empty",
        ],
        check=True,
    )
    file = tmp_path / "source.py"
    file.write_text("first")
    first = source_snapshot(tmp_path)
    file.write_text("second")
    second = source_snapshot(tmp_path)
    assert first["sha256"] != second["sha256"]
    subprocess.run(["git", "-C", str(tmp_path), "add", "source.py"], check=True)
    file.unlink()
    deleted = source_snapshot(tmp_path)
    assert deleted["sha256"] != second["sha256"]
    assert deleted["files"] == {"source.py": None}
    assert deleted["stable_during_capture"]


def test_inventory_whitelists_settings_and_does_not_start_runtime(
    tmp_path: Path,
) -> None:
    settings = tmp_path / "settings.json"
    settings.write_text(
        json.dumps(
            {
                "permissions": "PRIVATE",
                "command_model": {"model": "test:1", "secret": "PRIVATE"},
            }
        )
    )
    with patch(
        "scripts.commands.evaluation_contract._command", return_value=None
    ) as call:
        facts = environment_snapshot(ROOT / "nonexistent-test-store", settings)
    serialized = json.dumps(facts)
    assert "PRIVATE" not in serialized
    assert "permissions" not in serialized
    assert "test:1" in serialized
    assert [args.args[0][0] for args in call.call_args_list] == ["nvidia-smi", "ollama"]
    unmeasured = facts["unmeasured"]
    assert isinstance(unmeasured, dict)
    assert unmeasured["value"] is None


def test_duplicate_fields_and_existing_output_are_not_accepted(tmp_path: Path) -> None:
    path = tmp_path / "duplicate.json"
    path.write_text('{"version": 1, "version": 2}')
    with pytest.raises(ValueError, match="duplicate"):
        read_json(path)
    with pytest.raises(FileExistsError):
        write_new(path, {})


def test_concurrent_edit_with_unchanged_git_status_is_detected(tmp_path: Path) -> None:
    file = tmp_path / "untracked.py"
    file.write_text("first")
    calls = 0

    def changing_hash(path: Path) -> str:
        nonlocal calls
        result = file_hash(path)
        calls += 1
        if calls == 1:
            file.write_text("concurrent edit")
        return result

    def git_result(args: list[str], *, cwd: Path) -> bytes:
        assert cwd == tmp_path
        if args[1] == "ls-files":
            return b"untracked.py\0"
        if args[1] == "rev-parse":
            return b"unchanged-head"
        return b"?? untracked.py"

    with (
        patch("scripts.commands.evaluation_contract.file_hash", changing_hash),
        patch(
            "scripts.commands.evaluation_contract.subprocess.check_output", git_result
        ),
    ):
        snapshot = source_snapshot(tmp_path)
    assert not snapshot["stable_during_capture"]


def test_group_order_retains_repeated_attempts(plan: dict[str, Any]) -> None:
    original = binding(plan)
    repeated = dict(original, case_order=["open-clean", "open-clean"])
    assert group_key(repeated) != group_key(original)
