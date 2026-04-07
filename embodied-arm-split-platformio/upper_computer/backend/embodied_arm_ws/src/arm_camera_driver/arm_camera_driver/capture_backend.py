from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

MOCK_FRAME_ID = 'camera_optical_frame'
MOCK_FRAME_PAYLOAD = [[0]]


@dataclass
class CaptureFrame:
    """Serializable capture frame used by camera sources."""

    width: int
    height: int
    frame_id: str
    payload: Any


class CaptureBackend:
    """Minimal capture backend used by mock camera sources."""

    def __init__(self, source_type: str = 'mock') -> None:
        """Initialize the capture backend.

        Args:
            source_type: Capture backend source type.

        Returns:
            None.

        Raises:
            ValueError: If ``source_type`` is empty.
        """
        if not str(source_type).strip():
            raise ValueError('source_type must be non-empty')
        self.source_type = source_type

    def poll(self) -> CaptureFrame:
        """Return one mock capture frame.

        Args:
            None.

        Returns:
            CaptureFrame: Mock frame.

        Raises:
            Does not raise.
        """
        return CaptureFrame(width=640, height=480, frame_id=MOCK_FRAME_ID, payload=MOCK_FRAME_PAYLOAD)

    def stream(self, count: int = 1) -> Iterable[CaptureFrame]:
        """Yield a finite stream of mock frames.

        Args:
            count: Number of frames to yield.

        Returns:
            Iterable[CaptureFrame]: Mock frames.

        Raises:
            Does not raise.
        """
        for _ in range(max(1, count)):
            yield self.poll()
