"""Replay an existing STT JSON report through command decisions without OS actions.

App names supplied with --app form a controlled catalog fixture, not a scan of
the current desktop. The report can come from evaluate_offline_stt.py.
"""

import argparse
import json
from collections.abc import Mapping, Sequence
from pathlib import Path

from kyrin.actions.gate import ActionGate, ActionPolicy
from kyrin.actions.models import ActionNotice, ActionRequest
from kyrin.commands.coordinator import CommandCoordinator
from kyrin.commands.demo_interpreter import DemoCommandInterpreter
from kyrin.commands.models import CommandResolution, ResponseRequest
from kyrin.desktop.app_catalog import InstalledApp
from kyrin.desktop.spoken_app_names import CatalogSpokenAppResolver
from kyrin.responses.presenter import ResponsePresenter
from kyrin.stt.transcript import TranscriptStatus, TranscriptUpdate


class _FixtureCatalog:
    def __init__(self, app_names: Mapping[str, str]) -> None:
        self._apps = tuple(
            InstalledApp(f"fixture:{app_id}", name)
            for app_id, name in sorted(app_names.items())
        )

    def list_apps(self) -> tuple[InstalledApp, ...]:
        return self._apps

    def find_app(self, platform_id: str) -> InstalledApp | None:
        return next((app for app in self._apps if app.platform_id == platform_id), None)


def _parse_pairs(
    values: Sequence[str], option: str, parser: argparse.ArgumentParser
) -> dict[str, str]:
    pairs: dict[str, str] = {}
    for value in values:
        app_id, separator, name = value.partition("=")
        if not separator or not app_id.strip() or not name.strip():
            parser.error(f"{option} must be KYRIN_APP_ID=NAME")
        if app_id in pairs:
            parser.error(f"duplicate {option} app ID: {app_id}")
        pairs[app_id] = name
    return pairs


def _decide(
    text: str,
    language: str,
    resolver: CatalogSpokenAppResolver,
    policy: ActionPolicy,
) -> dict[str, object]:
    coordinator = CommandCoordinator(DemoCommandInterpreter(resolver))
    gate = ActionGate(policy)
    presenter = ResponsePresenter(language)
    events = coordinator.observe(
        TranscriptUpdate(0, text, TranscriptStatus.FINAL, language)
    )
    decision: dict[str, object] = {
        "intent": None,
        "response_kind": None,
        "response_text": None,
        "gate": "none",
    }
    for event in events:
        if isinstance(event, CommandResolution):
            if event.intent is not None:
                decision["intent"] = {
                    "kind": event.intent.kind.value,
                    "target": event.intent.target,
                    "app": event.intent.app,
                }
            gate_result = gate.observe(event)
            if isinstance(gate_result, ActionRequest):
                decision["gate"] = "authorized_dry_run"
            elif isinstance(gate_result, ActionNotice):
                decision["gate"] = f"blocked:{gate_result.reason.value}"
        elif isinstance(event, ResponseRequest):
            decision["response_kind"] = event.kind.value
            decision["response_text"] = presenter.present(event).text
    return decision


def replay(
    rows: Sequence[Mapping[str, str]],
    app_names: Mapping[str, str],
    aliases: Mapping[str, str] | None = None,
) -> list[dict[str, object]]:
    """Evaluate reference and STT text independently, one final turn per item."""
    if not rows:
        raise ValueError("STT report has no result rows")
    if not app_names:
        raise ValueError("at least one app fixture is required")
    catalog = _FixtureCatalog(app_names)
    bindings = {f"fixture:{app_id}": app_id for app_id in app_names}
    resolver = CatalogSpokenAppResolver(
        catalog,
        bindings,
        {app_id: (name,) for app_id, name in (aliases or {}).items()},
    )
    policy = ActionPolicy(allowed_apps=frozenset(app_names))
    output: list[dict[str, object]] = []
    for row in rows:
        item_id = row["id"]
        reference = row["reference"]
        transcript = row["transcript"]
        language = row["language"]
        output.append(
            {
                "id": item_id,
                "reference": reference,
                "transcript": transcript,
                "reference_decision": _decide(reference, language, resolver, policy),
                "transcript_decision": _decide(transcript, language, resolver, policy),
            }
        )
    return output


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stt-report", type=Path, required=True)
    parser.add_argument(
        "--app", action="append", required=True, metavar="KYRIN_APP_ID=NAME"
    )
    parser.add_argument("--alias", action="append", default=[], metavar="APP_ID=NAME")
    args = parser.parse_args(argv)
    apps = _parse_pairs(args.app, "--app", parser)
    aliases = _parse_pairs(args.alias, "--alias", parser)
    if any(app_id not in apps for app_id in aliases):
        parser.error("each --alias must refer to an --app ID")
    try:
        report = json.loads(args.stt_report.read_text(encoding="utf-8"))
        rows = report["results"]
        if not isinstance(rows, list) or not all(
            isinstance(row, dict)
            and all(
                isinstance(row.get(key), str)
                for key in ("id", "reference", "transcript", "language")
            )
            for row in rows
        ):
            raise ValueError("STT report has invalid result rows")
        decisions = replay(rows, apps, aliases)
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        parser.exit(2, f"Decision replay input error: {exc}\n")
    print(json.dumps({"items": decisions}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
