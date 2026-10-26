"""Short-lived evidence using GNOME's existing stable window token.

Generation identifies this observation, not an application or a replacement
window. Fresh location evidence must never renew the original request's age.
"""

import json
from collections.abc import Callable
from dataclasses import asdict, dataclass
from math import isfinite
from time import monotonic
from uuid import uuid4

from kyrin.vision.capture_geometry import MAX_CAPTURE_AGE_S, CaptureGeometry


@dataclass(frozen=True, slots=True)
class WindowObservation:
    app_id: str
    process_id: int
    window_token: str
    generation: str
    observed_at: float
    deadline: float

    def __post_init__(self) -> None:
        if (
            not self.app_id
            or self.process_id <= 0
            or not self.window_token
            or not self.generation
            or not isfinite(self.observed_at)
            or not isfinite(self.deadline)
            or not self.observed_at
            < self.deadline
            <= self.observed_at + MAX_CAPTURE_AGE_S
        ):
            raise ValueError("incomplete or unbounded window observation")

    @property
    def identity(self) -> tuple[str, int]:
        return self.app_id, self.process_id

    def current(self, token: str | None, now: float) -> bool:
        return token == self.window_token and self.observed_at <= now < self.deadline

    def to_json(self) -> str:
        return json.dumps(asdict(self), separators=(",", ":"))

    @classmethod
    def from_json(cls, value: str) -> WindowObservation:
        data = json.loads(value)
        if not isinstance(data, dict):
            raise ValueError("invalid window observation")
        return cls(**data)

    @classmethod
    def from_capture(
        cls, app_id: str, pid: int, geometry: CaptureGeometry
    ) -> WindowObservation:
        return cls(
            app_id,
            pid,
            geometry.window_token,
            geometry.capture_id,
            geometry.captured_at,
            geometry.captured_at + MAX_CAPTURE_AGE_S,
        )


def observe_window(
    identity_reader: Callable[[], tuple[str, int] | None],
    token_reader: Callable[[], str | None],
) -> WindowObservation | None:
    """Bracket identity with the existing token endpoint; no app-ID fallback."""
    started = monotonic()
    token = token_reader()
    identity = identity_reader()
    if not token or identity is None or token_reader() != token:
        return None
    observation = WindowObservation(
        *identity, token, uuid4().hex, started, started + MAX_CAPTURE_AGE_S
    )
    return observation if observation.current(token, monotonic()) else None
