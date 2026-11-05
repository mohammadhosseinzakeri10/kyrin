"""Serialize desktop captions and preserve explicit system-confirmation prompts."""

from collections.abc import Callable
from threading import RLock

from kyrin.responses.visual_status import VisualPresentation, power_presentation
from kyrin.system_power.flow import PowerPrompt, PowerStage


class VisualPresentationRouter:
    """Presentation priority only: never approves or submits a system action."""

    def __init__(self, publish: Callable[[VisualPresentation], None]) -> None:
        self._publish = publish
        self._lock = RLock()
        self._power: PowerPrompt | None = None
        self._current: VisualPresentation | None = None
        self._last_power_id = -1
        self._last_power_rank = -1

    def publish(self, presentation: VisualPresentation) -> None:
        with self._lock:
            if self._power is None:
                self._current = presentation
                self._publish(presentation)

    def publish_notice(self, notice: VisualPresentation) -> None:
        """Keep the primary activity/result while reporting an auxiliary problem."""
        with self._lock:
            if self._power is not None:
                return
            current = self._current
            self._publish(
                notice
                if current is None
                else VisualPresentation(
                    current.status, current.caption + " " + notice.caption
                )
            )

    def publish_power(self, prompt: PowerPrompt) -> bool:
        rank = {
            PowerStage.CHECKING: 0,
            PowerStage.FIRST: 1,
            PowerStage.SECOND: 2,
            PowerStage.SUBMITTING: 3,
            PowerStage.FINISHED: 4,
            PowerStage.CANCELLED: 4,
            PowerStage.EXPIRED: 4,
            PowerStage.FAILED: 4,
        }[prompt.stage]
        with self._lock:
            if prompt.request_id < self._last_power_id or (
                prompt.request_id == self._last_power_id
                and rank < self._last_power_rank
            ):
                return False
            self._last_power_id, self._last_power_rank = prompt.request_id, rank
            self._power = prompt if rank < 4 else None
            self._current = power_presentation(prompt)
            self._publish(self._current)
            return True
