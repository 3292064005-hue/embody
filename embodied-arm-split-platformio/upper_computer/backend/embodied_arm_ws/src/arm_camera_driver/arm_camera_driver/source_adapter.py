from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .capture_backend import CaptureBackend, CaptureFrame


@dataclass
class TopicFrame:
    """Frame wrapper used by topic-backed camera sources."""

    frame: CaptureFrame
    received_monotonic: float


class MockCameraSource:
    """Mock camera source backed by :class:`CaptureBackend`."""

    def __init__(self) -> None:
        """Initialize the mock source.

        Args:
            None.

        Returns:
            None.

        Raises:
            Does not raise.
        """
        self._backend = CaptureBackend(source_type='mock')

    def read_frame(self) -> CaptureFrame:
        """Return one mock frame.

        Args:
            None.

        Returns:
            CaptureFrame: Mock capture frame.

        Raises:
            Does not raise.
        """
        return self._backend.poll()

    def stream(self, count: int = 1) -> Iterable[CaptureFrame]:
        """Yield mock frames.

        Args:
            count: Number of frames to yield.

        Returns:
            Iterable[CaptureFrame]: Mock frames.

        Raises:
            Does not raise.
        """
        return self._backend.stream(count=count)


class TopicCameraSource:
    """Topic-backed source that stores the latest external frame."""

    def __init__(self) -> None:
        """Initialize the topic-backed source.

        Args:
            None.

        Returns:
            None.

        Raises:
            Does not raise.
        """
        self._latest: TopicFrame | None = None

    def update(self, frame: CaptureFrame, *, received_monotonic: float) -> None:
        """Store the latest external frame.

        Args:
            frame: Incoming capture frame.
            received_monotonic: Monotonic receive timestamp.

        Returns:
            None.

        Raises:
            ValueError: If ``frame`` is not a :class:`CaptureFrame`.
        """
        if not isinstance(frame, CaptureFrame):
            raise ValueError('frame must be a CaptureFrame instance')
        self._latest = TopicFrame(frame=frame, received_monotonic=received_monotonic)

    def read_frame(self) -> CaptureFrame:
        """Return the latest topic-backed frame.

        Args:
            None.

        Returns:
            CaptureFrame: Latest frame.

        Raises:
            RuntimeError: If no frame has been received yet.
        """
        if self._latest is None:
            raise RuntimeError('no topic frame available')
        return self._latest.frame
