from __future__ import annotations

from typing import Any, Iterable

from .detection_providers import DetectionProvider, detect_targets


class QRCodeDetector:
    """Detector component with explicit input/output contract.

    The detector itself only owns detector-name semantics and provider routing.
    Concrete detection extraction happens through the registered providers so
    synthetic targets, external live detections, and future detector backends
    do not need separate detector entrypoints.
    """

    def __init__(self, *, providers: Iterable[DetectionProvider] | None = None) -> None:
        self._providers = tuple(providers or ())

    def detect(self, frame: Any) -> list[dict[str, Any]]:
        if frame is None:
            raise ValueError('frame must not be None')
        return detect_targets(frame, detector_name='qrcode', providers=self._providers or None)
