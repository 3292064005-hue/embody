from __future__ import annotations

from typing import Any

from .synthetic_targets import extract_synthetic_targets


class QRCodeDetector:
    """Detector component with explicit input/output contract."""

    def detect(self, frame: Any) -> list[dict[str, Any]]:
        if frame is None:
            raise ValueError('frame must not be None')
        return extract_synthetic_targets(frame, detector_name='qrcode')
