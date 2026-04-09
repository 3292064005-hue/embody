from __future__ import annotations

from typing import Any


class PregraspBuilder:
    """Build a normalized pre-grasp command description."""

    def build(self, candidate: dict[str, Any], approach_height_m: float = 0.12, *, frame: str = 'table') -> dict[str, Any]:
        """Build a pre-grasp description from the selected candidate.

        Args:
            candidate: Selected grasp candidate.
            approach_height_m: Approach height above the grasp pose.
            frame: Pose frame identifier.

        Returns:
            dict[str, Any]: Normalized pre-grasp description.

        Raises:
            ValueError: If inputs are invalid.
        """
        if not isinstance(candidate, dict):
            raise ValueError('candidate must be a dictionary')
        if approach_height_m <= 0.0:
            raise ValueError('approach_height_m must be positive')
        return {
            **dict(candidate),
            'frame': str(frame),
            'approach_height_m': float(approach_height_m),
            'pregrasp_z': float(candidate.get('grasp_z', 0.03)) + float(approach_height_m),
        }
