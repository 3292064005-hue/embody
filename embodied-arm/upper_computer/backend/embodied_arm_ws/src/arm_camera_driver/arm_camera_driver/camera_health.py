from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class CameraHealthMonitor:
    """Track camera liveness and stream-health counters for diagnostics."""

    expected_fps: float = 15.0
    reconnect_ms: int = 2000
    last_frame_monotonic: float = 0.0
    device_open: bool = False
    streaming: bool = False
    dropped_frame_count: int = 0
    reconnect_count: int = 0

    def frame_received(self, now: float) -> None:
        """Record the latest frame reception timestamp.

        Args:
            now: Monotonic timestamp when the frame was received.

        Returns:
            None.

        Raises:
            ValueError: If ``now`` is negative.
        """
        if now < 0.0:
            raise ValueError('now must be non-negative')
        self.last_frame_monotonic = now
        self.device_open = True
        self.streaming = True

    def device_opened(self) -> None:
        """Mark the camera device as opened.

        Args:
            None.

        Returns:
            None.

        Raises:
            Does not raise.
        """
        self.device_open = True

    def device_closed(self) -> None:
        """Mark the camera device as closed.

        Args:
            None.

        Returns:
            None.

        Raises:
            Does not raise.
        """
        self.device_open = False
        self.streaming = False

    def frame_dropped(self) -> None:
        """Record a dropped frame event.

        Args:
            None.

        Returns:
            None.

        Raises:
            Does not raise.
        """
        self.dropped_frame_count += 1

    def reconnect_attempted(self) -> None:
        """Record a reconnect attempt.

        Args:
            None.

        Returns:
            None.

        Raises:
            Does not raise.
        """
        self.reconnect_count += 1

    def healthy(self, now: float, stale_after_sec: float = 1.0) -> bool:
        """Return whether the camera is still considered alive.

        Args:
            now: Current monotonic timestamp.
            stale_after_sec: Freshness threshold.

        Returns:
            bool: Whether the camera is alive.

        Raises:
            ValueError: If ``now`` or ``stale_after_sec`` are invalid.
        """
        if now < 0.0:
            raise ValueError('now must be non-negative')
        if stale_after_sec < 0.0:
            raise ValueError('stale_after_sec must be non-negative')
        if not self.device_open or not self.streaming or self.last_frame_monotonic <= 0.0:
            return False
        return (now - self.last_frame_monotonic) <= stale_after_sec

    def snapshot(self, now: float, stale_after_sec: float = 1.0) -> dict[str, Any]:
        """Return a serializable camera-health snapshot.

        Args:
            now: Current monotonic timestamp.
            stale_after_sec: Freshness threshold.

        Returns:
            dict[str, Any]: Camera-health snapshot.

        Raises:
            ValueError: If inputs are invalid.
        """
        age_sec = max(0.0, now - self.last_frame_monotonic) if self.last_frame_monotonic else float('inf')
        healthy = self.healthy(now, stale_after_sec) if self.last_frame_monotonic else False
        return {
            'cameraAlive': healthy,
            'lastFrameAgeSec': None if age_sec == float('inf') else age_sec,
            'expectedFps': self.expected_fps,
            'reconnectMs': self.reconnect_ms,
            'deviceOpen': self.device_open,
            'streaming': self.streaming,
            'droppedFrameCount': self.dropped_frame_count,
            'reconnectCount': self.reconnect_count,
        }
