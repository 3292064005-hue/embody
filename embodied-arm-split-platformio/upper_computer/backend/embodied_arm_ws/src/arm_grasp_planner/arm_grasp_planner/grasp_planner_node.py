from __future__ import annotations

import json
import time
from typing import Any

try:
    import rclpy
    from arm_backend_common.lifecycle_support import ManagedLifecycleNode, lifecycle_main, ros_io_enabled
    from std_msgs.msg import String
    from arm_common import TopicNames
except Exception:  # pragma: no cover
    rclpy = None
    ManagedLifecycleNode = object

    def lifecycle_main(factory, args=None):
        del factory, args
        raise RuntimeError('rclpy unavailable')

    def ros_io_enabled(*, enable_ros_io: bool, message_cls=None):
        del message_cls
        return False

    String = object

    class TopicNames:
        INTERNAL_GENERATE_GRASPS = '/arm/internal/generate_grasps'
        GRASP_PLAN_SUMMARY = '/arm/grasp/summary'

from arm_backend_common.data_models import TargetSnapshot

from .candidate_generator import CandidateGenerator
from .candidate_ranker import CandidateRanker
from .fallback_strategy import FallbackStrategy
from .place_pose_builder import PlacePoseBuilder
from .pregrasp_builder import PregraspBuilder


class GraspPlannerNode(ManagedLifecycleNode):
    """Runtime grasp planner that generates, ranks, and selects candidates."""

    def __init__(self, *, enable_ros_io: bool = True) -> None:
        """Initialize grasp planning helpers and ROS I/O when available.

        Args:
            enable_ros_io: Whether ROS publishers/subscriptions should be created.

        Returns:
            None.

        Raises:
            Does not raise directly.
        """
        self._ros_enabled = ros_io_enabled(enable_ros_io=enable_ros_io, message_cls=String)
        if self._ros_enabled:
            super().__init__('grasp_planner')
        self.generator = CandidateGenerator()
        self.ranker = CandidateRanker()
        self.pregrasp = PregraspBuilder()
        self.place_pose = PlacePoseBuilder()
        self.fallback = FallbackStrategy()
        self._last_plan: dict[str, Any] = {'status': 'idle'}
        self._summary_pub = self.create_managed_publisher(String, TopicNames.GRASP_PLAN_SUMMARY, 10) if self._ros_enabled else None
        if self._ros_enabled:
            self.create_subscription(String, TopicNames.INTERNAL_GENERATE_GRASPS, self._on_generate_grasps, 20)

    def plan(
        self,
        target: TargetSnapshot | dict[str, Any],
        place_zone: dict[str, Any] | None = None,
        *,
        failed_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        """Generate, rank, and select grasp candidates.

        Args:
            target: Target snapshot or dictionary.
            place_zone: Optional placement zone.
            failed_ids: Candidate identifiers that should be skipped.

        Returns:
            dict[str, Any]: Runtime grasp-plan summary.

        Raises:
            ValueError: If inputs are invalid.
        """
        normalized_target = self._normalize_target(target)
        normalized_place = self._normalize_place_zone(place_zone or {})
        ranked = self.ranker.rank(self.generator.generate(normalized_target))
        best = self.fallback.next_candidate(ranked, failed_ids=failed_ids)
        plan = {
            'status': 'planned',
            'selectedTargetKey': normalized_target.key(),
            'candidate': self.pregrasp.build(best or {}),
            'candidateCount': len(ranked),
            'place': normalized_place,
            'rankedCandidates': ranked,
            'updatedAt': round(time.time(), 3),
        }
        self._last_plan = plan
        self._publish_plan()
        return dict(plan)

    def last_plan(self) -> dict[str, Any]:
        """Return the last generated grasp plan."""
        return dict(self._last_plan)

    def _normalize_target(self, target: TargetSnapshot | dict[str, Any]) -> TargetSnapshot:
        """Normalize a target payload into a :class:`TargetSnapshot`."""
        if isinstance(target, TargetSnapshot):
            return target
        if not isinstance(target, dict) or not target:
            raise ValueError('target must be a TargetSnapshot or non-empty dictionary')
        return TargetSnapshot(
            target_id=str(target.get('target_id', '')),
            target_type=str(target.get('target_type', target.get('type', 'unknown'))),
            semantic_label=str(target.get('semantic_label', target.get('label', target.get('target_type', 'unknown')))),
            table_x=float(target.get('table_x', target.get('x', 0.0))),
            table_y=float(target.get('table_y', target.get('y', 0.0))),
            yaw=float(target.get('yaw', 0.0)),
            confidence=float(target.get('confidence', 0.0)),
        )

    def _normalize_place_zone(self, place_zone: dict[str, Any]) -> dict[str, Any]:
        """Normalize a placement payload."""
        return self.place_pose.build(place_zone)

    def _publish_plan(self) -> None:
        if self._ros_enabled and not self.runtime_active:
            return
        """Publish the last plan when ROS publishers are available."""
        if self._summary_pub is None or String is object:
            return
        self._summary_pub.publish(String(data=json.dumps(self._last_plan, ensure_ascii=False)))

    def _on_generate_grasps(self, msg: String) -> None:
        if self._ros_enabled and not self.runtime_active:
            return
        """Handle a serialized grasp-generation request."""
        payload = self._parse_json(msg.data)
        if not payload:
            return
        self.plan(payload.get('target') or {}, payload.get('place') or {}, failed_ids=list(payload.get('failedIds') or []))

    @staticmethod
    def _parse_json(payload: str) -> dict[str, Any]:
        """Parse a JSON payload into a dictionary."""
        if not payload:
            return {}
        try:
            parsed = json.loads(payload)
        except Exception:
            return {}
        return parsed if isinstance(parsed, dict) else {}


def main(args=None) -> None:
    """Run the grasp planner node when ROS is available."""
    if rclpy is None:
        GraspPlannerNode(enable_ros_io=False)
        return
    lifecycle_main(GraspPlannerNode, args=args)
