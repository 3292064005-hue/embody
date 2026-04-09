from __future__ import annotations

from typing import Any


class TargetFuser:
    """Fuse detector outputs into one ordered target list."""

    @staticmethod
    def _target_key(item: dict[str, Any]) -> str:
        return str(item.get('target_id') or f"{item.get('target_type', 'unknown')}:{item.get('semantic_label', item.get('label', 'unknown'))}:{round(float(item.get('x', item.get('table_x', 0.0))), 3)}:{round(float(item.get('y', item.get('table_y', 0.0))), 3)}")

    def fuse(self, *target_sets: list[dict[str, Any]]) -> list[dict[str, Any]]:
        fused: dict[str, dict[str, Any]] = {}
        for target_set in target_sets:
            if not isinstance(target_set, list):
                raise ValueError('target sets must be lists')
            for item in target_set:
                if not isinstance(item, dict):
                    continue
                normalized = dict(item)
                key = self._target_key(normalized)
                current = fused.get(key)
                if current is None or float(normalized.get('confidence', 0.0)) >= float(current.get('confidence', 0.0)):
                    fused[key] = normalized
        ordered = list(fused.values())
        ordered.sort(key=lambda item: (-float(item.get('confidence', 0.0)), str(item.get('target_id', '')) or self._target_key(item)))
        return ordered
