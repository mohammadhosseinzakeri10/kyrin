"""Match spoken names against explicitly bound, registered applications."""

import re
import unicodedata
from collections.abc import Mapping, Sequence
from difflib import SequenceMatcher

from kyrin.commands.app_names import SpokenAppCandidate, SpokenAppMatch
from kyrin.desktop.app_catalog import AppCatalog


def _normalize(name: str) -> str:
    name = unicodedata.normalize("NFKC", name).casefold()
    name = name.replace("ي", "ی").replace("ك", "ک")
    return " ".join(re.findall(r"[^\W_]+", name, flags=re.UNICODE))


class CatalogSpokenAppResolver:
    """Suggest only bound apps; approximate suggestions always require a reply."""

    def __init__(
        self,
        catalog: AppCatalog,
        app_ids: Mapping[str, str],
        aliases: Mapping[str, Sequence[str]] | None = None,
    ) -> None:
        if any(
            not external.strip() or not internal.strip()
            for external, internal in app_ids.items()
        ):
            raise ValueError("app identifiers must not be empty")
        if aliases is not None and any(
            app_id not in app_ids.values()
            or any(not _normalize(alias) for alias in values)
            for app_id, values in aliases.items()
        ):
            raise ValueError("aliases must name bound apps and contain text")
        self._catalog = catalog
        self._app_ids = dict(app_ids)
        self._aliases = {key: tuple(values) for key, values in (aliases or {}).items()}
        self._names: dict[str, tuple[SpokenAppCandidate, set[str]]] = {}
        self.refresh()

    def refresh(self) -> None:
        """Refresh after installation/removal, outside the live audio callback."""
        names: dict[str, tuple[SpokenAppCandidate, set[str]]] = {}
        for installed in self._catalog.list_apps():
            app_id = self._app_ids.get(installed.platform_id)
            if app_id is None:
                continue
            _, spellings = names.setdefault(
                app_id, (SpokenAppCandidate(app_id, installed.display_name), set())
            )
            spellings.add(_normalize(installed.display_name))
            spellings.add(_normalize(app_id))
            spellings.update(
                _normalize(alias) for alias in self._aliases.get(app_id, ())
            )
        self._names = names

    def resolve(self, spoken_name: str) -> SpokenAppMatch:
        return self._match(spoken_name, allow_weak_suggestion=False)

    def suggest(self, spoken_name: str) -> SpokenAppMatch:
        """Allow weaker names only as candidates for an explicit question."""
        return self._match(spoken_name, allow_weak_suggestion=True)

    def _match(
        self, spoken_name: str, *, allow_weak_suggestion: bool
    ) -> SpokenAppMatch:
        name = _normalize(spoken_name)
        if not name:
            return SpokenAppMatch()
        exact = tuple(
            candidate
            for candidate, spellings in self._names.values()
            if name in spellings
        )
        if exact:
            return SpokenAppMatch(exact, exact=True)

        scores: list[tuple[float, SpokenAppCandidate]] = []
        for candidate, spellings in self._names.values():
            score = max(
                (
                    SequenceMatcher(None, name, spelling).ratio()
                    for spelling in spellings
                    if spelling
                ),
                default=0.0,
            )
            if allow_weak_suggestion:
                compact_name = name.replace(" ", "")
                score = max(
                    score,
                    max(
                        (
                            SequenceMatcher(
                                None, compact_name, spelling.replace(" ", "")
                            ).ratio()
                            for spelling in spellings
                            if spelling
                        ),
                        default=0.0,
                    ),
                )
            scores.append((score, candidate))
        scores.sort(key=lambda item: (-item[0], item[1].app_id))
        if not scores:
            return SpokenAppMatch()
        best = scores[0][0]
        # Longer, speech-split names can be suggested at a lower score. Fuzzy
        # matches never authorize an action: the interpreter must ask first.
        proposal_threshold = (
            0.70
            if allow_weak_suggestion and len(name.replace(" ", "")) >= 5
            else 0.82
        )
        if best < proposal_threshold:
            return SpokenAppMatch()
        near = tuple(candidate for score, candidate in scores if score >= best - 0.08)
        return SpokenAppMatch(near)
