from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class PerceptionHealthMonitor:
    """Track perception liveness for readiness bridging."""

    last_success_monotonic: float = 0.0
    error_count: int = 0

    def mark_success(self, now: float) -> None:
        """Mark a successful perception cycle.

        Args:
            now: Monotonic timestamp.

        Returns:
            None.

        Raises:
            ValueError: If ``now`` is negative.
        """
        if now < 0.0:
            raise ValueError('now must be non-negative')
        self.last_success_monotonic = now

    def mark_error(self) -> None:
        """Increment the perception error counter.

        Args:
            None.

        Returns:
            None.

        Raises:
            Does not raise.
        """
        self.error_count += 1

    def snapshot(self, *, now: float, stale_after_sec: float) -> dict[str, Any]:
        """Return a serializable liveness snapshot.

        Args:
            now: Current monotonic timestamp.
            stale_after_sec: Freshness threshold.

        Returns:
            dict[str, Any]: Perception liveness snapshot.

        Raises:
            ValueError: If ``stale_after_sec`` is invalid.
        """
        if stale_after_sec <= 0.0:
            raise ValueError('stale_after_sec must be positive')
        alive = self.last_success_monotonic > 0.0 and (now - self.last_success_monotonic) <= stale_after_sec
        return {'perceptionAlive': alive, 'lastSuccessMonotonic': self.last_success_monotonic or None, 'errorCount': self.error_count}
