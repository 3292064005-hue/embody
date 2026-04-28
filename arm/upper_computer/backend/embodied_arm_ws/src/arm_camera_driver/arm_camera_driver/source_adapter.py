from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .capture_backend import CaptureBackend, CaptureFrame, DEFAULT_MOCK_PROFILE


@dataclass
class TopicFrame:
    """Frame wrapper used by topic-backed camera sources."""

    frame: CaptureFrame
    received_monotonic: float


class MockCameraSource:
    """Mock camera source backed by :class:`CaptureBackend`."""

    def __init__(self, *, mock_profile: str = DEFAULT_MOCK_PROFILE) -> None:
        self._backend = CaptureBackend(source_type='mock', mock_profile=mock_profile)

    def read_frame(self) -> CaptureFrame:
        return self._backend.poll()

    def stream(self, count: int = 1) -> Iterable[CaptureFrame]:
        return self._backend.stream(count=count)


class TopicCameraSource:
    """Topic-backed source that stores the latest external frame."""

    def __init__(self) -> None:
        self._latest: TopicFrame | None = None

    def update(self, frame: CaptureFrame, *, received_monotonic: float) -> None:
        if not isinstance(frame, CaptureFrame):
            raise ValueError('frame must be a CaptureFrame instance')
        self._latest = TopicFrame(frame=frame, received_monotonic=received_monotonic)

    def read_frame(self) -> CaptureFrame:
        if self._latest is None:
            raise RuntimeError('no topic frame available')
        return self._latest.frame
