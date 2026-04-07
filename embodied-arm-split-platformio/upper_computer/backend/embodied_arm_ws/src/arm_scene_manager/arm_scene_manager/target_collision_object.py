from __future__ import annotations

from typing import Any


class TargetCollisionObjectBuilder:
    """Build normalized collision objects from perception targets."""

    def build(self, target: dict[str, Any]) -> dict[str, Any]:
        """Convert a target dictionary into a collision-object description.

        Args:
            target: Target dictionary.

        Returns:
            dict[str, Any]: Collision object description.

        Raises:
            ValueError: If ``target`` is invalid.
        """
        if not isinstance(target, dict) or not target:
            raise ValueError('target must be a non-empty dictionary')
        target_id = str(target.get('target_id', '')).strip() or 'unknown'
        target_type = str(target.get('target_type', target.get('type', 'box'))).strip() or 'box'
        return {
            'id': target_id,
            'frame': str(target.get('frame', 'table')),
            'shape': target_type,
            'dimensions': {
                'x': float(target.get('size_x', 0.04)),
                'y': float(target.get('size_y', 0.04)),
                'z': float(target.get('size_z', 0.06)),
            },
            'pose': {
                'x': float(target.get('table_x', target.get('x', 0.0))),
                'y': float(target.get('table_y', target.get('y', 0.0))),
                'z': float(target.get('z', 0.03)),
                'yaw': float(target.get('yaw', 0.0)),
            },
            'metadata': {
                'semanticLabel': str(target.get('semantic_label', target.get('label', ''))),
                'confidence': float(target.get('confidence', 0.0)),
            },
        }
