from __future__ import annotations

import time
from typing import Any

from arm_backend_common.data_models import TargetSnapshot

from .candidate_generator import CandidateGenerator
from .candidate_ranker import CandidateRanker
from .fallback_strategy import FallbackStrategy
from .place_pose_builder import PlacePoseBuilder
from .pregrasp_builder import PregraspBuilder


class GraspPlanningService:
    """Pure grasp-planning service shared by the planner and ROS node adapters.

    The service owns candidate generation/ranking without creating ROS node
    instances. Runtime node wrappers publish the resulting summaries, while
    non-ROS callers can reuse the same logic through this deterministic API.
    """

    provider_mode = 'embedded_core'
    authoritative = False

    def __init__(self, *, provider_mode: str = 'embedded_core', authoritative: bool = False, source_authority: str | None = None) -> None:
        """Initialize candidate-planning helpers.

        Returns:
            None.

        Raises:
            Does not raise.
        """
        self.provider_mode = str(provider_mode or 'embedded_core')
        self.authoritative = bool(authoritative)
        self._source_authority = str(source_authority or self.provider_mode or 'embedded_core')
        self.generator = CandidateGenerator()
        self.ranker = CandidateRanker()
        self.pregrasp = PregraspBuilder()
        self.place_pose = PlacePoseBuilder()
        self.fallback = FallbackStrategy()
        self._plan_counter = 0
        self._last_plan: dict[str, Any] = {'status': 'idle'}

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
            place_zone: Optional placement zone description.
            failed_ids: Candidate identifiers that should be skipped.

        Returns:
            dict[str, Any]: Runtime grasp-plan summary with provider metadata.

        Raises:
            ValueError: If the target or place zone is invalid.
        """
        normalized_target = self._normalize_target(target)
        normalized_place = self._normalize_place_zone(place_zone or {})
        ranked = self.ranker.rank(self.generator.generate(normalized_target))
        best = self.fallback.next_candidate(ranked, failed_ids=failed_ids)
        self._plan_counter += 1
        candidate_batch_id = f'grasp-{self._plan_counter:06d}'
        plan = {
            'status': 'planned',
            'selectedTargetKey': normalized_target.key(),
            'candidateBatchId': candidate_batch_id,
            'providerMode': self.provider_mode,
            'providerAuthoritative': self.authoritative,
            'sourceAuthority': self._source_authority,
            'candidate': self.pregrasp.build(best or {}),
            'candidateCount': len(ranked),
            'place': normalized_place,
            'rankedCandidates': ranked,
            'updatedAt': round(time.time(), 3),
        }
        self._last_plan = plan
        return dict(plan)

    def last_plan(self) -> dict[str, Any]:
        """Return the most recent grasp plan.

        Returns:
            dict[str, Any]: Last computed plan.

        Raises:
            Does not raise.
        """
        return dict(self._last_plan)

    def _normalize_target(self, target: TargetSnapshot | dict[str, Any]) -> TargetSnapshot:
        """Normalize a target payload into :class:`TargetSnapshot`.

        Args:
            target: Target snapshot or raw dictionary.

        Returns:
            TargetSnapshot: Normalized target.

        Raises:
            ValueError: If the target is empty or unsupported.
        """
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
        """Normalize a placement payload.

        Args:
            place_zone: Placement payload.

        Returns:
            dict[str, Any]: Normalized placement description.

        Raises:
            ValueError: If downstream normalization rejects the payload.
        """
        return self.place_pose.build(place_zone)
