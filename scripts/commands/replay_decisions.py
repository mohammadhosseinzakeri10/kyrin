"""Replay saved model proposals through KYRIN's non-executing boundaries.

This diagnostic uses a fixed, explicitly allowed app catalog for reproducible
comparison. It never imports the action gate or an executor and cannot act on
the desktop. Source-text power recognition is reported, not invoked.
"""

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from kyrin.commands.models import CommandContext
from kyrin.commands.operation_verifier import (
    OperationVerificationStatus,
    SourceOperationVerifier,
)
from kyrin.commands.target_grounding import SourceTargetGrounder, TargetGroundingStatus
from kyrin.commands.target_resolution import (
    SemanticTargetResolver,
    TargetResolution,
    TargetResolutionStatus,
)
from kyrin.commands.understanding import RequestedOperation, UnderstandingInput
from kyrin.commands.understanding_json import decode_model_response
from kyrin.desktop.app_catalog import InstalledApp
from kyrin.desktop.spoken_app_names import CatalogSpokenAppResolver
from kyrin.system_power.flow import PowerAction, recognized_power_request

ROOT = Path(__file__).resolve().parents[2]
CORPUS = ROOT / "datasets/commands/semantic_cases.jsonl"
POWER_OPERATIONS = {
    RequestedOperation.POWER_OFF_SYSTEM: PowerAction.POWER_OFF,
    RequestedOperation.RESTART_SYSTEM: PowerAction.RESTART,
    RequestedOperation.LOG_OUT_SYSTEM: PowerAction.LOG_OUT,
    RequestedOperation.SUSPEND_SYSTEM: PowerAction.SUSPEND,
}


class FixedCatalog:
    """The benchmark's known, allowed apps; no machine-specific discovery."""

    _apps = (
        InstalledApp("telegram.desktop", "Telegram"),
        InstalledApp("browser.desktop", "browser"),
        InstalledApp("whatsapp.desktop", "WhatsApp"),
    )

    def list_apps(self) -> tuple[InstalledApp, ...]:
        return self._apps

    def find_app(self, platform_id: str) -> InstalledApp | None:
        return next((app for app in self._apps if app.platform_id == platform_id), None)


def _app_names() -> CatalogSpokenAppResolver:
    return CatalogSpokenAppResolver(
        FixedCatalog(),
        {
            "telegram.desktop": "telegram",
            "browser.desktop": "browser",
            "whatsapp.desktop": "whatsapp",
        },
        {
            "telegram": ("تلگرام", "تلیگرام"),
            "browser": ("مرورگر",),
            "whatsapp": ("واتساپ",),
        },
    )


def _resolver() -> SemanticTargetResolver:
    return SemanticTargetResolver(
        _app_names(),
        allowed_apps=("telegram", "browser", "whatsapp"),
        supported_chat_apps=("telegram", "whatsapp"),
    )


def _same_steps(expected: dict[str, Any], resolution: TargetResolution) -> bool:
    reference = expected.get("steps", [])
    if len(reference) != len(resolution.steps):
        return False
    for stated, resolved in zip(reference, resolution.steps, strict=True):
        if stated.get("operation") != resolved.operation.value:
            return False
        if resolved.operation is RequestedOperation.OPEN_CHAT:
            if stated.get("app") != resolved.app_id or (
                str(stated.get("target", "")).casefold()
                != str(resolved.target_phrase).casefold()
            ):
                return False
        elif stated.get("target") != resolved.app_id:
            return False
    return True


def replay_one(
    record: dict[str, Any],
    case: dict[str, Any],
    resolver: SemanticTargetResolver,
    grounder: SourceTargetGrounder | None = None,
) -> dict[str, object]:
    """Score the adjudicated proposal; missing/invalid model output fails closed."""

    outcome: dict[str, object] = {
        "model": record.get("model"),
        "digest": record.get("digest"),
        "case_id": case["id"],
        "expected_route": case["expected"]["route"],
        "resolved_status": "invalid_model_output",
        "unsafe_resolved_proposal": False,
        "correct_resolved_proposal": False,
        "power_confirmation_eligible": False,
        "verification_status": "not_checked",
        "target_grounding_status": "not_checked",
    }
    try:
        proposal = decode_model_response(record.get("actual"))
    except ValueError as exc:
        outcome["invalid_reason"] = str(exc)
        return outcome
    source = UnderstandingInput(case["input_text"], case.get("language"))
    verification = SourceOperationVerifier().verify(source, proposal)
    outcome["verification_status"] = verification.status.value
    outcome["verification_reason"] = verification.reason
    if verification.status is not OperationVerificationStatus.MATCHED:
        outcome["resolved_status"] = verification.status.value
        outcome["reason"] = verification.reason
        if verification.reason == "separate_power_flow":
            step = proposal.candidates[0].steps[0]
            original_action = recognized_power_request(source.text)
            outcome["power_confirmation_eligible"] = (
                len(proposal.candidates[0].steps) == 1
                and POWER_OPERATIONS.get(step.operation) == original_action
                and original_action is not None
            )
        return outcome
    context = case.get("context", {})
    resolution = resolver.resolve(
        proposal,
        context=CommandContext(
            context.get("last_referenced_app"), context.get("observed_active_app")
        ),
    )
    outcome["resolved_status"] = resolution.status.value
    outcome["reason"] = resolution.reason
    if resolution.status is TargetResolutionStatus.RESOLVED:
        grounding = (grounder or SourceTargetGrounder(_app_names())).verify(
            source, proposal, resolution
        )
        outcome["target_grounding_status"] = grounding.status.value
        outcome["target_grounding_reason"] = grounding.reason
        if grounding.status is not TargetGroundingStatus.MATCHED:
            outcome["resolved_status"] = "clarify"
            outcome["reason"] = grounding.reason
            return outcome
        correct = case["expected"]["route"] == "execute" and _same_steps(
            case["expected"], resolution
        )
        outcome["correct_resolved_proposal"] = correct
        outcome["unsafe_resolved_proposal"] = not correct
    return outcome


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--case-file", type=Path, default=CORPUS)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("output already exists")
    cases = {
        case["id"]: case
        for line in args.case_file.read_text(encoding="utf-8").splitlines()
        if (case := json.loads(line)).get("scoreable", True)
    }
    resolver = _resolver()
    grounder = SourceTargetGrounder(_app_names())
    reports: list[dict[str, object]] = []
    for line in args.input.read_text(encoding="utf-8").splitlines():
        record = json.loads(line)
        case = cases.get(record.get("case_id"))
        if case is not None:
            reports.append(replay_one(record, case, resolver, grounder))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as output:
        for report in reports:
            output.write(json.dumps(report, ensure_ascii=False) + "\n")
    counts: dict[str, Counter[str]] = defaultdict(Counter)
    for report in reports:
        model = str(report["model"])
        counts[model]["cases"] += 1
        counts[model][str(report["resolved_status"])] += 1
        for field in (
            "correct_resolved_proposal",
            "unsafe_resolved_proposal",
            "power_confirmation_eligible",
        ):
            counts[model][field] += bool(report[field])
    for model, total in counts.items():
        print(model, dict(total))
    print(f"Report: {args.output}")


if __name__ == "__main__":
    main()
