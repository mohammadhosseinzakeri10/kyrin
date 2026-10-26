"""Shared Unicode and case normalization for comparing spoken and visible text."""

import re
import unicodedata


def fold_case(value: str) -> str:
    """Normalize Unicode and ignore letter case without changing the original text."""
    return unicodedata.normalize("NFKC", value).casefold()


def source_spelling(source: str, target: str) -> str:
    """Recover a verified target's original letter case from its source text."""
    parts = target.split()
    if not parts:
        return target
    pattern = r"(?<!\w)" + r"\s+".join(re.escape(part) for part in parts) + r"(?!\w)"
    expected = " ".join(fold_case(target).split())
    for match in reversed(tuple(re.finditer(pattern, source, flags=re.IGNORECASE))):
        spelling = match.group()
        if " ".join(fold_case(spelling).split()) == expected:
            return spelling
    return target
