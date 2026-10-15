"""Match spoken names against the device catalog before permission filtering."""

import re
import unicodedata
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from difflib import SequenceMatcher

from kyrin.commands.app_names import SpokenAppCandidate, SpokenAppMatch
from kyrin.desktop.app_catalog import AppCatalog


@dataclass(slots=True)
class _RegisteredName:
    platform_id: str
    candidate: SpokenAppCandidate | None
    spellings: set[str]
    user_spellings: set[str]


def _normalize(name: str) -> str:
    name = unicodedata.normalize("NFKC", name).casefold()
    name = name.replace("ي", "ی").replace("ك", "ک")
    return " ".join(re.findall(r"[^\W_]+", name, flags=re.UNICODE))


def _abbreviations(name: str) -> tuple[str, ...]:
    """Derive names like VS Code from a registered three-word display name."""
    words = _normalize(name).split()
    if len(words) < 3 or not all(word[0].isalpha() for word in words):
        return ()
    prefix = "".join(word[0] for word in words[:-1])
    return (
        f"{prefix} {words[-1]}",
        f"{prefix}{words[-1]}",
        "".join(word[0] for word in words),
    )


def _split_camel_case(name: str) -> str:
    """Allow speech recognition to separate words in a registered brand name."""
    return re.sub(r"(?<=[a-z])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])", " ", name)


def _sound_key(name: str) -> str:
    """A conservative Latin sound hint used only for suggestions."""
    compact = _normalize(name).replace(" ", "")
    if not compact.isascii() or len(compact) < 5:
        return ""
    compact = re.sub(r"(?<=[a-z])(?:two|too|tor(?=r)|to)(?=[a-z])", "2", compact)
    key = re.sub(r"[aeiouy]", "", compact)
    return key if len(key) >= 3 else ""


class CatalogSpokenAppResolver:
    """Use every registered name to avoid suggesting a different allowed app.

    Only explicitly bound apps can leave this resolver as command candidates.
    Approximate suggestions still require a user reply in the interpreter.
    """

    def __init__(
        self,
        catalog: AppCatalog,
        app_ids: Mapping[str, str],
        aliases: Mapping[str, Sequence[str]] | None = None,
        *,
        registered_aliases: Mapping[str, Sequence[str]] | None = None,
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
        if registered_aliases is not None and any(
            not platform_id.strip() or any(not _normalize(alias) for alias in values)
            for platform_id, values in registered_aliases.items()
        ):
            raise ValueError("registered aliases must have an app ID and text")
        self._catalog = catalog
        self._app_ids = dict(app_ids)
        self._aliases = {key: tuple(values) for key, values in (aliases or {}).items()}
        self._registered_aliases = {
            key: tuple(values) for key, values in (registered_aliases or {}).items()
        }
        self._names: dict[str, tuple[SpokenAppCandidate, set[str]]] = {}
        self._registered_names: tuple[_RegisteredName, ...] = ()
        self._browser_candidates: tuple[SpokenAppCandidate, ...] = ()
        self.refresh()

    def refresh(self) -> None:
        """Refresh after installation/removal, outside the live audio callback."""
        names: dict[str, tuple[SpokenAppCandidate, set[str]]] = {}
        registered: list[_RegisteredName] = []
        browser_ids: set[str] = set()
        for installed in self._catalog.list_apps():
            app_id = self._app_ids.get(installed.platform_id)
            user_spellings = {
                _normalize(alias)
                for alias in self._registered_aliases.get(installed.platform_id, ())
            }
            spellings = {
                _normalize(installed.display_name),
                _normalize(_split_camel_case(installed.display_name)),
            }
            spellings.update(_abbreviations(installed.display_name))
            spellings.update(_normalize(name) for name in installed.alternate_names)
            spellings.update(user_spellings)
            candidate = (
                SpokenAppCandidate(app_id, installed.display_name)
                if app_id is not None
                else None
            )
            if app_id is not None:
                spellings.add(_normalize(app_id))
                spellings.update(
                    _normalize(alias) for alias in self._aliases.get(app_id, ())
                )
            registered.append(
                _RegisteredName(
                    installed.platform_id, candidate, spellings, user_spellings
                )
            )
            if app_id is None:
                continue
            if "WebBrowser" in installed.categories:
                browser_ids.add(app_id)
            _, allowed_spellings = names.setdefault(
                app_id, (SpokenAppCandidate(app_id, installed.display_name), set())
            )
            allowed_spellings.update(spellings)
        self._names = names
        self._registered_names = tuple(registered)
        self._browser_candidates = tuple(
            sorted(
                (names[app_id][0] for app_id in browser_ids),
                key=lambda candidate: (
                    candidate.display_name.casefold(),
                    candidate.app_id,
                ),
            )
        )

    def browser_candidates(self) -> tuple[SpokenAppCandidate, ...]:
        """Return only permitted installed apps registered as web browsers."""
        return self._browser_candidates

    def vocabulary_hints(self, limit: int = 16) -> tuple[str, ...]:
        """Give STT bounded, non-executable names from allowed registrations."""
        if not 0 <= limit <= 16:
            raise ValueError("vocabulary hint limit must be between 0 and 16")
        full_names: list[str] = []
        abbreviations: list[str] = []
        for candidate, _ in sorted(
            self._names.values(), key=lambda item: item[0].display_name.casefold()
        ):
            name = candidate.display_name
            if (
                3 <= len(_normalize(name).split()) <= 5
                and len(name) <= 64
                and re.fullmatch(r"[\w ]+", name, flags=re.UNICODE)
            ):
                full_names.append(name)
                words = name.split()
                initials = "".join(word[0] for word in words[:-1]).upper()
                short = f"{initials} {words[-1]}"
                if len(short) <= 64:
                    abbreviations.append(short)
        return tuple(dict.fromkeys((*full_names, *abbreviations)))[:limit]

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
        # A user can select which duplicate registration owns its own display
        # name. An alias borrowing another app's name cannot override it.
        user_exact = tuple(
            entry for entry in self._registered_names if name in entry.user_spellings
        )
        if (
            len(user_exact) == 1
            and user_exact[0].candidate is not None
            and name == _normalize(user_exact[0].candidate.display_name)
        ):
            return SpokenAppMatch((user_exact[0].candidate,), exact=True)
        exact = tuple(
            entry for entry in self._registered_names if name in entry.spellings
        )
        if exact:
            if any(entry.candidate is None for entry in exact):
                return SpokenAppMatch()
            return SpokenAppMatch(
                tuple(
                    dict.fromkeys(
                        entry.candidate
                        for entry in exact
                        if entry.candidate is not None
                    )
                ),
                exact=True,
            )

        scores: list[tuple[float, _RegisteredName]] = []
        sound_key = _sound_key(name) if allow_weak_suggestion else ""
        for entry in self._registered_names:
            spellings = entry.spellings
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
                if sound_key and any(
                    _sound_key(spelling) == sound_key for spelling in spellings
                ):
                    score = max(score, 0.85)
            scores.append((score, entry))
        scores.sort(key=lambda item: (-item[0], item[1].platform_id))
        if not scores:
            return SpokenAppMatch()
        best = scores[0][0]
        # Longer, speech-split names can be suggested at a lower score. Fuzzy
        # matches never authorize an action: the interpreter must ask first.
        proposal_threshold = (
            0.70 if allow_weak_suggestion and len(name.replace(" ", "")) >= 5 else 0.82
        )
        if best < proposal_threshold:
            return SpokenAppMatch()
        near = tuple(entry for score, entry in scores if score >= best - 0.08)
        if any(entry.candidate is None for entry in near):
            return SpokenAppMatch()
        return SpokenAppMatch(
            tuple(
                dict.fromkeys(
                    entry.candidate for entry in near if entry.candidate is not None
                )
            )
        )
