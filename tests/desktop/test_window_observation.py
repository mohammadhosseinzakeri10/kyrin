"""Window identity never degrades to process/app matching or renewed evidence."""

from dataclasses import replace

import pytest

from kyrin.desktop import window_observation
from kyrin.desktop.window_observation import WindowObservation, observe_window


@pytest.mark.parametrize("tokens", [(None, None), ("7", "8"), ("7", None)])
def test_missing_or_switched_token_cannot_supply_evidence(
    tokens: tuple[str | None, str | None],
) -> None:
    values = iter(tokens)
    assert observe_window(lambda: ("example.desktop", 42), lambda: next(values)) is None


def test_generations_are_distinct_and_original_deadline_is_absolute(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(window_observation, "monotonic", lambda: 100.0)
    first = observe_window(lambda: ("example.desktop", 42), lambda: "7")
    second = observe_window(lambda: ("example.desktop", 42), lambda: "7")
    assert first is not None and second is not None
    assert first.generation != second.generation
    assert first.deadline == 110
    assert WindowObservation.from_json(first.to_json()) == first
    assert first.current("7", 109.99)
    assert not first.current("7", 110)
    assert not first.current("8", 101)
    assert not first.current("7", 99)
    with pytest.raises(ValueError):
        replace(first, deadline=111)
