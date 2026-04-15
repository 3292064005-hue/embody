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
        metadata = dict(source_metadata or {})
        payload = summary.get('payload') if isinstance(summary.get('payload'), dict) else {}
        provenance = dict(payload.get('visualProvenance') or {}) if isinstance(payload, dict) else {}
        summary['timestampSec'] = timestamp_sec
        summary['sourceMetadata'] = metadata
        summary['metadata'] = metadata
        summary['sourceType'] = str(metadata.get('sourceType', payload.get('sourceType', 'unknown')) or 'unknown')
        if provenance:
            summary['sourceClass'] = str(provenance.get('sourceClass', payload.get('sourceClass', 'unknown')) or 'unknown')
            summary['frameIngressLive'] = bool(provenance.get('frameIngressLive', payload.get('frameIngressLive', False)))
            summary['cameraLive'] = bool(provenance.get('cameraLive', payload.get('cameraLive', False)))
            summary['renderablePreview'] = bool(provenance.get('renderablePreview', payload.get('renderablePreview', False)))
            summary['visualProvenance'] = provenance
        return summary
