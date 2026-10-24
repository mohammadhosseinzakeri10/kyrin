"""Build a short-lived, identity-bound catalog for language understanding."""

import json
import logging
import re
import subprocess
from collections import Counter
from collections.abc import Callable
from difflib import SequenceMatcher
from pathlib import Path
from time import monotonic, perf_counter
from typing import Literal, Protocol

from kyrin.actions.visible_control import VisibleTextOption
from kyrin.commands.visible_options import VisibleOption
from kyrin.desktop.accessibility_target import AccessibilityTarget
from kyrin.desktop.platforms.gnome import read_active_window_token
from kyrin.desktop.window_observation import WindowObservation, observe_window
from kyrin.text_normalization import fold_case
from kyrin.vision.text_targets import normalize_phrase

ACCESSIBILITY_HELPER = Path(__file__).with_name("desktop_accessibility_inventory.py")
_LOGGER = logging.getLogger(__name__)


def _spoken_similarity(label: str, utterance: str) -> float:
    name = fold_case(label).split()
    words = fold_case(utterance).split()
    if not name or not words:
        return 0.0
    length = len(name)
    return max(
        SequenceMatcher(
            None, " ".join(name), " ".join(words[index : index + size])
        ).ratio()
        for size in {max(1, length - 1), length, length + 1}
        for index in range(max(1, len(words) - size + 1))
    )


class VisibleTextReader(Protocol):
    def ready(self) -> bool: ...
    def list_visible_text(
        self, app_id: str, pid: int
    ) -> tuple[VisibleTextOption, ...]: ...


class DesktopControlInventory:
    def __init__(
        self,
        identity_reader: Callable[[], tuple[str, int] | None],
        verifier: VisibleTextReader | None = None,
        *,
        helper_path: Path = ACCESSIBILITY_HELPER,
        system_python: str = "/usr/bin/python3",
        token_reader: Callable[[], str | None] | None = None,
    ) -> None:
        self._identity_reader = identity_reader
        self._token_reader = token_reader or read_active_window_token
        self._verifier = verifier
        self._helper_path = helper_path
        self._system_python = system_python

    def read_options(
        self, expected_app: str, utterance: str = ""
    ) -> tuple[VisibleOption, ...]:
        observation = observe_window(self._identity_reader, self._token_reader)
        identity = observation.identity if observation is not None else None
        if observation is None or identity is None or identity[0] != expected_app:
            return ()
        assert observation is not None and identity is not None
        ocr_observations: dict[tuple[str, tuple[int, int]], WindowObservation] = {}
        observed: list[
            tuple[
                str,
                Literal["accessibility", "ocr"],
                str | None,
                bool | None,
                tuple[int, int] | None,
            ]
        ] = []
        structures: dict[str, AccessibilityTarget] = {}
        accessibility_started = perf_counter()
        try:
            result = subprocess.run(
                [
                    self._system_python,
                    str(self._helper_path),
                    *map(str, identity),
                    observation.window_token,
                ],
                capture_output=True,
                text=True,
                timeout=6,
                check=False,
            )
            payload = json.loads(result.stdout) if result.returncode == 0 else []
        except OSError, subprocess.TimeoutExpired, ValueError:
            payload = []
        accessibility_seconds = perf_counter() - accessibility_started
        if accessibility_seconds >= 1.0:
            _LOGGER.warning(
                "Focused control accessibility scan took %.1fs",
                accessibility_seconds,
            )
        if isinstance(payload, list):
            for item in payload[:300]:
                if not isinstance(item, dict):
                    continue
                label = item.get("label")
                role = item.get("role")
                checked = item.get("checked")
                x = item.get("x")
                y = item.get("y")
                if (
                    isinstance(label, str)
                    and 1 <= len(label.strip()) <= 80
                    and (role is None or isinstance(role, str))
                    and (checked is None or type(checked) is bool)
                    and (
                        (type(x) is int and x >= 0 and type(y) is int and y >= 0)
                        or (x is None and y is None)
                    )
                ):
                    raw_target = item.get("accessibility")
                    if raw_target is not None:
                        try:
                            if not isinstance(raw_target, str):
                                continue
                            structures[label.strip()] = AccessibilityTarget.from_json(
                                raw_target
                            )
                        except ValueError, TypeError:
                            continue
                    observed.append(
                        (
                            label.strip(),
                            "accessibility",
                            role,
                            checked,
                            (x, y) if type(x) is int and type(y) is int else None,
                        )
                    )
        # A unique accessible name quoted in the request is sufficient. Read
        # OCR only when that quick route cannot identify an intended option.
        source = fold_case(utterance)
        accessible_names = [
            fold_case(label)
            for label, option_source, _, _, _ in observed
            if option_source == "accessibility"
        ]
        accessible_counts = Counter(accessible_names)
        has_named_match = any(
            accessible_counts[name] == 1
            and len(name) >= 3
            and re.search(rf"(?<!\w){re.escape(name)}(?!\w)", source)
            for name in accessible_names
        )
        if (
            not has_named_match
            and self._verifier is not None
            and self._verifier.ready()
        ):
            ocr_started = perf_counter()
            for item in self._verifier.list_visible_text(*identity):
                if item.geometry is None or not 1 <= len(item.label.strip()) <= 80:
                    continue
                evidence = WindowObservation.from_capture(*identity, item.geometry)
                if not evidence.current(observation.window_token, monotonic()):
                    return ()
                ocr_observations[(item.label.strip(), item.anchor)] = evidence
                observed.append((item.label.strip(), "ocr", None, None, item.anchor))
            ocr_seconds = perf_counter() - ocr_started
            if ocr_seconds >= 1.0:
                _LOGGER.warning("Focused control OCR took %.1fs", ocr_seconds)
        if self._identity_reader() != identity or not observation.current(
            self._token_reader(), monotonic()
        ):
            return ()
        # A repeated name is not a unique click target. Multiple OCR readings
        # of the same accessible label count as one observed control.
        accessibility_counts = Counter(
            fold_case(label)
            for label, source, _, _, _ in observed
            if source == "accessibility"
        )
        ocr_counts = Counter(
            normalize_phrase(label)
            for label, source, _, _, _ in observed
            if source == "ocr"
        )
        selected: list[
            tuple[
                str,
                Literal["accessibility", "ocr"],
                str | None,
                bool | None,
                tuple[int, int] | None,
            ]
        ] = []
        seen: set[str] = set()
        for label, source, role, checked, anchor in observed:
            key = fold_case(label)
            if key in seen:
                continue
            if source == "accessibility":
                if accessibility_counts[key] != 1:
                    continue
            elif accessibility_counts[key] or ocr_counts[normalize_phrase(label)] != 1:
                continue
            seen.add(key)
            selected.append((label, source, role, checked, anchor))
        if len(selected) > 100:
            ranked = sorted(
                range(len(selected)),
                key=lambda index: _spoken_similarity(selected[index][0], utterance),
                reverse=True,
            )
            primary = ranked[:70]
            primary_set = set(primary)
            remainder = [
                index for index in range(len(selected)) if index not in primary_set
            ]
            stride = max(1, len(remainder) // 30)
            selected = [
                selected[index] for index in (primary + remainder[::stride][:30])[:100]
            ]
        return tuple(
            VisibleOption(
                str(index),
                label,
                source,
                role,
                checked,
                anchor,
                observation
                if source == "accessibility"
                else ocr_observations.get((label, anchor))
                if anchor is not None
                else None,
                structures.get(label) if source == "accessibility" else None,
            )
            for index, (label, source, role, checked, anchor) in enumerate(
                selected, start=1
            )
        )
