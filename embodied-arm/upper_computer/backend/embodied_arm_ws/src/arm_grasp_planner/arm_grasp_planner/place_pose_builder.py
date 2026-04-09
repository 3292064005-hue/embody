from __future__ import annotations

from typing import Any


class PlacePoseBuilder:
    """Normalize placement targets for the runtime chain."""

    def build(self, place_zone: dict[str, Any], *, frame: str = 'table') -> dict[str, float | str]:
        """Build a normalized place pose.

        Args:
            place_zone: Raw placement dictionary.
            frame: Pose frame identifier.

        Returns:
            dict[str, float | str]: Normalized place pose.

        Raises:
            ValueError: If ``place_zone`` is invalid.
        """
        if not isinstance(place_zone, dict):
            raise ValueError('place_zone must be a dictionary')
        return {
            'frame': str(frame),
            'x': float(place_zone.get('x', 0.2)),
            'y': float(place_zone.get('y', 0.0)),
            'z': float(place_zone.get('z', 0.05)),
            'yaw': float(place_zone.get('yaw', 0.0)),
        }
