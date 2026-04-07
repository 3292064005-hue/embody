from __future__ import annotations

from typing import Any


class ContourDetector:
    """Detector component with explicit input/output contract."""

    def detect(self, frame: Any) -> list[dict[str, Any]]:
        """Detect contour-based targets from one frame.

        Args:
            frame: Input frame payload.

        Returns:
            list[dict[str, Any]]: Detected targets.

        Raises:
            ValueError: If ``frame`` is None.
        """
        if frame is None:
            raise ValueError('frame must not be None')
        return []
