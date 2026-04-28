from __future__ import annotations

import time
from typing import Any

from arm_backend_common.data_models import TargetSnapshot

from .preprocess import ImagePreprocessor
from .color_detector import ColorDetector
from .qrcode_detector import QRCodeDetector
from .contour_detector import ContourDetector
from .synthetic_targets import describe_frame_visual_source
from .target_filter import TargetFilter
from .target_fuser import TargetFuser
from .target_tracker import TargetTracker
from .debug_draw import DebugDrawer
from .health import PerceptionHealthMonitor

DEFAULT_STALE_AFTER_SEC = 2.0


class PerceptionNode:
    """Perception runtime that tracks liveness and target availability."""

    def __init__(self, *, stale_after_sec: float = DEFAULT_STALE_AFTER_SEC, min_seen_count: int = 1) -> None:
        """Initialize the perception node.

        Args:
            stale_after_sec: Freshness threshold for liveness.
            min_seen_count: Minimum observations for tracker acceptance.

        Returns:
            None.

        Raises:
            ValueError: If configuration values are invalid.
        """
        if stale_after_sec <= 0.0:
            raise ValueError('stale_after_sec must be positive')
        self.preprocess = ImagePreprocessor()
        self.color = ColorDetector()
        self.qrcode = QRCodeDetector()
        self.contour = ContourDetector()
        self.filter = TargetFilter()
        self.fuser = TargetFuser()
        self.tracker = TargetTracker(stale_after_sec=stale_after_sec, min_seen_count=min_seen_count)
        self.drawer = DebugDrawer()
        self.health = PerceptionHealthMonitor()
        self.stale_after_sec = float(stale_after_sec)
        self._last_process_monotonic = 0.0
        self._last_targets: list[dict[str, Any]] = []

    def _to_target_snapshot(self, item: dict[str, Any], now: float) -> TargetSnapshot:
        """Convert one detector payload into a target snapshot.

        Args:
            item: Detector payload.
            now: Monotonic timestamp.

        Returns:
            TargetSnapshot: Converted target snapshot.

        Raises:
            ValueError: If the detector payload is invalid.
        """
        if not isinstance(item, dict):
            raise ValueError('detector output must be a dictionary')
        return TargetSnapshot(
            target_id=str(item.get('target_id', '')),
            target_type=str(item.get('target_type', item.get('type', 'unknown'))),
            semantic_label=str(item.get('semantic_label', item.get('label', item.get('target_type', 'unknown')))),
            table_x=float(item.get('table_x', item.get('x', 0.0))),
            table_y=float(item.get('table_y', item.get('y', 0.0))),
            yaw=float(item.get('yaw', 0.0)),
            confidence=float(item.get('confidence', 0.0)),
            image_u=float(item.get('image_u', item.get('u', 0.0))),
            image_v=float(item.get('image_v', item.get('v', 0.0))),
            received_monotonic=now,
        )

    def receive_frame(self, frame: Any, *, now: float | None = None) -> dict[str, Any]:
        """Process one runtime frame and return a health summary.

        Args:
            frame: Incoming frame payload.
            now: Optional monotonic timestamp.

        Returns:
            dict[str, Any]: Perception summary.

        Raises:
            ValueError: If the frame is invalid.
        """
        return self.process_summary(frame, now=now)

    def process(self, frame: Any, *, now: float | None = None) -> list[dict[str, Any]]:
        """Run one perception pass and return filtered targets.

        Args:
            frame: Input frame payload.
            now: Optional monotonic timestamp.

        Returns:
            list[dict[str, Any]]: Filtered target payloads.

        Raises:
            ValueError: If frame or detector outputs are invalid.
        """
        timestamp = time.monotonic() if now is None else now
        normalized = self.preprocess.normalize(frame)
        fused = self.fuser.fuse(self.color.detect(normalized), self.qrcode.detect(normalized), self.contour.detect(normalized))
        filtered = self.filter.filter(fused)
        snapshots = [self._to_target_snapshot(item, timestamp) for item in filtered]
        self.tracker.ingest_batch(snapshots, now=timestamp)
        self._last_targets = [item.copy() for item in filtered]
        self._last_process_monotonic = timestamp
        self.health.mark_success(timestamp)
        return filtered

    def current_targets(self, *, now: float | None = None) -> list[dict[str, Any]]:
        """Return the current tracker-backed target list.

        Args:
            now: Optional monotonic timestamp used for stale pruning.

        Returns:
            list[dict[str, Any]]: Tracker-backed public target payloads.

        Raises:
            Does not raise.
        """
        return [target.to_dict() for target in self.tracker.get_graspable(now)]

    def primary_target(self, *, now: float | None = None) -> dict[str, Any] | None:
        """Return the highest-priority currently graspable target.

        Args:
            now: Optional monotonic timestamp used for stale pruning.

        Returns:
            dict[str, Any] | None: The best target or ``None``.

        Raises:
            Does not raise.
        """
        targets = self.current_targets(now=now)
        return dict(targets[0]) if targets else None

    def process_summary(self, frame: Any, *, now: float | None = None) -> dict[str, Any]:
        """Run one perception pass and return enriched liveness metadata.

        Args:
            frame: Input frame payload.
            now: Optional monotonic timestamp.

        Returns:
            dict[str, Any]: Perception summary.

        Raises:
            ValueError: If frame or detector outputs are invalid.
        """
        timestamp = time.monotonic() if now is None else now
        try:
            observed_targets = self.process(frame, now=timestamp)
        except Exception:
            self.health.mark_error()
            raise
        tracker_health = self.tracker.health_snapshot(now=timestamp)
        perception_health = self.health.snapshot(now=timestamp, stale_after_sec=self.stale_after_sec)
        stable_targets = self.current_targets(now=timestamp)
        visual_source = describe_frame_visual_source(frame)
        return {
            'observedTargets': observed_targets,
            'targets': stable_targets,
            'primaryTarget': self.primary_target(now=timestamp),
            **perception_health,
            **tracker_health,
            'processedAtMonotonic': self._last_process_monotonic,
            'frameProvenance': visual_source,
            'detectionSourceMode': str(visual_source.get('detectionSourceMode', 'unknown')),
            'authoritativeVisualSource': str(visual_source.get('authoritativeTargetSource', 'unknown')),
        }

    def health_snapshot(self, now: float | None = None, stale_after_sec: float | None = None) -> dict[str, Any]:
        """Return liveness and target-availability summary for readiness bridging.

        Args:
            now: Optional monotonic timestamp.
            stale_after_sec: Optional override freshness threshold.

        Returns:
            dict[str, Any]: Combined perception and tracker health snapshot.

        Raises:
            ValueError: If the stale threshold is invalid.
        """
        timestamp = time.monotonic() if now is None else now
        freshness = self.stale_after_sec if stale_after_sec is None else stale_after_sec
        snapshot = self.health.snapshot(now=timestamp, stale_after_sec=freshness)
        current_targets = self.current_targets(now=timestamp)
        return {
            **snapshot,
            **self.tracker.health_snapshot(now=timestamp),
            'targetCount': len(current_targets),
            'primaryTarget': self.primary_target(now=timestamp),
        }



def main(args=None) -> None:
    _ = args
    node = PerceptionNode()
    node.process([[0]])
