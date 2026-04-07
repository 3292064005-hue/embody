from __future__ import annotations

from typing import Any

from arm_backend_common.data_models import TargetSnapshot


class CandidateGenerator:
    """Build grasp candidates from normalized target summaries."""

    def generate(self, target: TargetSnapshot | dict[str, Any]) -> list[dict[str, Any]]:
        """Generate one or more grasp candidates.

        Args:
            target: Target snapshot or dictionary.

        Returns:
            list[dict[str, Any]]: Candidate list.

        Raises:
            ValueError: If ``target`` is invalid.
        """
        if isinstance(target, TargetSnapshot):
            target_data = target.to_dict()
        elif isinstance(target, dict) and target:
            target_data = dict(target)
        else:
            raise ValueError('target must be a TargetSnapshot or non-empty dictionary')
        confidence = float(target_data.get('confidence', 0.0))
        yaw = float(target_data.get('yaw', 0.0))
        target_id = str(target_data.get('target_id', '')).strip() or 'unknown'
        table_x = float(target_data.get('table_x', target_data.get('x', 0.0)))
        table_y = float(target_data.get('table_y', target_data.get('y', 0.0)))
        semantic_label = str(target_data.get('semantic_label', target_data.get('label', target_data.get('target_type', 'unknown'))))
        return [
            {
                'candidate_id': f'{target_id}:top_down',
                'target_id': target_id,
                'semantic_label': semantic_label,
                'score': confidence,
                'yaw': yaw,
                'approach': 'top_down',
                'grasp_x': table_x,
                'grasp_y': table_y,
            },
            {
                'candidate_id': f'{target_id}:angled_positive',
                'target_id': target_id,
                'semantic_label': semantic_label,
                'score': round(confidence * 0.95, 4),
                'yaw': yaw + 0.15,
                'approach': 'angled_positive',
                'grasp_x': table_x,
                'grasp_y': table_y,
            },
            {
                'candidate_id': f'{target_id}:angled_negative',
                'target_id': target_id,
                'semantic_label': semantic_label,
                'score': round(confidence * 0.95, 4),
                'yaw': yaw - 0.15,
                'approach': 'angled_negative',
                'grasp_x': table_x,
                'grasp_y': table_y,
            },
        ]
