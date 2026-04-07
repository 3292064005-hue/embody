from __future__ import annotations

from typing import Any


class TargetFilter:
    """Filter raw detector candidates according to confidence thresholds."""

    def filter(self, targets: list[dict[str, Any]], threshold: float = 0.5) -> list[dict[str, Any]]:
        """Filter raw targets.

        Args:
            targets: Raw target candidates.
            threshold: Minimum accepted confidence.

        Returns:
            list[dict[str, Any]]: Filtered targets.

        Raises:
            ValueError: If inputs are invalid.
        """
        if not isinstance(targets, list):
            raise ValueError('targets must be a list')
        if threshold < 0.0:
            raise ValueError('threshold must be non-negative')
        filtered: list[dict[str, Any]] = []
        for item in targets:
            if not isinstance(item, dict):
                continue
            if float(item.get('confidence', 0.0)) >= threshold:
                filtered.append(dict(item))
        return filtered
