from __future__ import annotations

from typing import Any


class ImagePreprocessor:
    """Normalize incoming perception frames without changing their schema."""

    def normalize(self, frame: Any) -> Any:
        """Normalize one frame for downstream detectors.

        Args:
            frame: Input frame payload.

        Returns:
            Any: Normalized frame payload.

        Raises:
            ValueError: If ``frame`` is None.
        """
        if frame is None:
            raise ValueError('frame must not be None')
        return frame
