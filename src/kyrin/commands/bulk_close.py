"""Exact bulk scope is rules-only; it must never come from phonetic repair."""

import re

from kyrin.text_normalization import fold_case


def bulk_close_target(text: str) -> str | None:
    phrase = fold_case(text).strip().rstrip(".!?؟")
    match = re.fullmatch(r"(?:please )?close all (?:windows of )?(.+)", phrase)
    return match[1].strip() if match else None


def has_bulk_close_prefix(text: str) -> bool:
    return bool(re.match(r"^(?:please )?close all\b", fold_case(text).strip()))
