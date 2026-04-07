from __future__ import annotations

from typing import Any


class StaticSceneBuilder:
    """Build deterministic static planning-scene objects.

    The builder remains intentionally lightweight while producing a richer scene
    representation than the earlier placeholder table-only dictionary.
    """

    def build(
        self,
        *,
        table_length: float = 0.6,
        table_width: float = 0.4,
        table_height: float = 0.0,
        guard_padding: float = 0.05,
        frame: str = 'world',
    ) -> dict[str, Any]:
        """Return a static planning-scene snapshot.

        Args:
            table_length: Table length in meters.
            table_width: Table width in meters.
            table_height: Table top height in meters.
            guard_padding: Workspace-guard padding in meters.
            frame: Scene reference frame.

        Returns:
            dict[str, Any]: Static scene snapshot.

        Raises:
            ValueError: If geometric inputs are invalid.
        """
        values = {
            'table_length': float(table_length),
            'table_width': float(table_width),
            'table_height': float(table_height),
            'guard_padding': float(guard_padding),
        }
        if values['table_length'] <= 0.0 or values['table_width'] <= 0.0:
            raise ValueError('table dimensions must be positive')
        if values['guard_padding'] < 0.0:
            raise ValueError('guard_padding must be non-negative')
        return {
            'frame': str(frame),
            'objects': [
                {
                    'id': 'table',
                    'frame': str(frame),
                    'shape': 'box',
                    'dimensions': {
                        'x': values['table_length'],
                        'y': values['table_width'],
                        'z': max(0.01, values['table_height'] + 0.02),
                    },
                    'pose': {
                        'x': 0.0,
                        'y': 0.0,
                        'z': values['table_height'] - 0.01,
                        'yaw': 0.0,
                    },
                },
                {
                    'id': 'workspace_guard',
                    'frame': str(frame),
                    'shape': 'box',
                    'dimensions': {
                        'x': values['table_length'] + values['guard_padding'] * 2.0,
                        'y': values['table_width'] + values['guard_padding'] * 2.0,
                        'z': 0.4,
                    },
                    'pose': {
                        'x': 0.0,
                        'y': 0.0,
                        'z': values['table_height'] + 0.2,
                        'yaw': 0.0,
                    },
                },
            ],
        }
