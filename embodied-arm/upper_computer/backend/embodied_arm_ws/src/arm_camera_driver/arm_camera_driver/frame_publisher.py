from __future__ import annotations

from dataclasses import asdict
from typing import Any

from .capture_backend import CaptureFrame


class FramePublisher:
    """Serialize capture frames into HMI-friendly summaries."""

    def to_summary(self, frame: CaptureFrame, *, timestamp_sec: float | None = None, source_metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        """Convert a frame into a serializable summary.

        Args:
            frame: Capture frame to serialize.
            timestamp_sec: Optional wall-clock timestamp.
            source_metadata: Optional source metadata.

        Returns:
            dict[str, Any]: Serialized frame summary.

        Raises:
            ValueError: If ``frame`` is not a :class:`CaptureFrame`.
        """
        if not isinstance(frame, CaptureFrame):
            raise ValueError('frame must be a CaptureFrame instance')
        summary = asdict(frame)
        summary['timestampSec'] = timestamp_sec
        summary['sourceMetadata'] = dict(source_metadata or {})
        summary['metadata'] = dict(source_metadata or {})
        return summary
