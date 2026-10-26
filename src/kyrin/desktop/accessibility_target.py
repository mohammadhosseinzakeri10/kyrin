"""Structural identity of a control within one observed window subtree."""

from __future__ import annotations

import json
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class AccessibilityTarget:
    # Each entry is (child index, role, accessible name), starting at the window.
    ancestry: tuple[tuple[int, str, str], ...]

    def __post_init__(self) -> None:
        if (
            not self.ancestry
            or len(self.ancestry) > 100
            or any(
                type(index) is not int or index < 0 or not role
                for index, role, _name in self.ancestry
            )
        ):
            raise ValueError("invalid accessible ancestry")

    def to_json(self) -> str:
        return json.dumps(self.ancestry, ensure_ascii=False)

    @classmethod
    def from_json(cls, raw: str) -> AccessibilityTarget:
        value = json.loads(raw)
        if not isinstance(value, list) or not all(
            isinstance(item, list)
            and len(item) == 3
            and type(item[0]) is int
            and isinstance(item[1], str)
            and isinstance(item[2], str)
            for item in value
        ):
            raise ValueError("invalid accessible ancestry")
        return cls(tuple((item[0], item[1], item[2]) for item in value))
