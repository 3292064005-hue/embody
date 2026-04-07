from __future__ import annotations

from typing import Any


class TargetFuser:
    """Fuse detector outputs into one ordered target list."""

    def fuse(self, *target_sets: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Fuse target sets while preserving individual target payloads.

        Args:
            *target_sets: Detector output lists.

        Returns:
            list[dict[str, Any]]: Fused target list.

        Raises:
            ValueError: If a target set is not a list.
        """
        fused: list[dict[str, Any]] = []
        for target_set in target_sets:
            if not isinstance(target_set, list):
                raise ValueError('target sets must be lists')
            for item in target_set:
                if isinstance(item, dict):
                    fused.append(dict(item))
        return fused
