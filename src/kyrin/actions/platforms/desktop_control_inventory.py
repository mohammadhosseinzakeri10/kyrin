"""Build a short-lived, identity-bound catalog for language understanding."""

import json
import logging
import re
import subprocess
from collections import Counter
from collections.abc import Callable
from difflib import SequenceMatcher
from pathlib import Path
from time import perf_counter
from typing import Literal, Protocol

from kyrin.actions.visible_control import VisibleTextOption
from kyrin.commands.visible_options import VisibleOption
from kyrin.text_normalization import fold_case

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
        verifier: VisibleTextReader,
        *,
        helper_path: Path = ACCESSIBILITY_HELPER,
        system_python: str = "/usr/bin/python3",
    ) -> None:
        self._identity_reader = identity_reader
        self._verifier = verifier
        self._helper_path = helper_path
        self._system_python = system_python

    def read_options(
        self, expected_app: str, utterance: str = ""
    ) -> tuple[VisibleOption, ...]:
        identity = self._identity_reader()
        if (
            identity is None
            or identity[0] != expected_app
            or not self._verifier.ready()
        ):
            return ()
        observed: list[
            tuple[
                str,
                Literal["accessibility", "ocr"],
                str | None,
                bool | None,
                tuple[int, int] | None,
            ]
        ] = []
        accessibility_started = perf_counter()
        try:
            result = subprocess.run(
                [self._system_python, str(self._helper_path), *map(str, identity)],
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
                    and type(x) is int
                    and x >= 0
                    and type(y) is int
                    and y >= 0
                ):
                    observed.append(
                        (label.strip(), "accessibility", role, checked, (x, y))
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
        if not has_named_match:
            ocr_started = perf_counter()
            observed.extend(
                (item.label.strip(), "ocr", None, None, item.anchor)
                for item in self._verifier.list_visible_text(*identity)
                if 1 <= len(item.label.strip()) <= 80
            )
            ocr_seconds = perf_counter() - ocr_started
            if ocr_seconds >= 1.0:
                _LOGGER.warning("Focused control OCR took %.1fs", ocr_seconds)
        if self._identity_reader() != identity:
            return ()
        # A repeated name is not a unique click target. Multiple OCR readings
        # of the same accessible label count as one observed control.
        accessibility_counts = Counter(
            fold_case(label)
            for label, source, _, _, _ in observed
            if source == "accessibility"
        )
        ocr_counts = Counter(
            fold_case(label) for label, source, _, _, _ in observed if source == "ocr"
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
            elif accessibility_counts[key] or ocr_counts[key] != 1:
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
            VisibleOption(str(index), label, source, role, checked, anchor)
            for index, (label, source, role, checked, anchor) in enumerate(
                selected, start=1
            )
        )
