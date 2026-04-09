from __future__ import annotations

import time
from typing import Any

from arm_common import TopicNames

DEFAULT_CAMERA_TOPIC = getattr(TopicNames, 'CAMERA_IMAGE')

from .camera_health import CameraHealthMonitor
from .capture_backend import CaptureFrame, DEFAULT_MOCK_PROFILE
from .frame_publisher import FramePublisher
from .source_adapter import MockCameraSource, TopicCameraSource

DEFAULT_STALE_AFTER_SEC = 1.0


class CameraDriverNode:
    """Camera runtime bridge that produces frame and health summaries."""

    def __init__(self, source_type: str = 'mock', *, topic_name: str = DEFAULT_CAMERA_TOPIC, device_index: int = 0, expected_fps: float = 15.0, stale_after_sec: float = DEFAULT_STALE_AFTER_SEC, reconnect_ms: int = 2000, mock_profile: str = DEFAULT_MOCK_PROFILE) -> None:
        """Initialize the camera driver node.

        Args:
            source_type: Camera source type, currently ``mock`` or ``topic``.
            topic_name: Topic name used by topic-backed sources.
            device_index: Reserved device index for future hardware sources.
            expected_fps: Expected frame rate.
            stale_after_sec: Freshness threshold used for liveness.
            reconnect_ms: Reconnect interval in milliseconds.
            mock_profile: Structured mock-scene profile for mock sources.

        Returns:
            None.

        Raises:
            ValueError: If configuration values are invalid.
        """
        if source_type not in {'mock', 'topic'}:
            raise ValueError('source_type must be mock or topic')
        if expected_fps <= 0.0:
            raise ValueError('expected_fps must be positive')
        if stale_after_sec <= 0.0:
            raise ValueError('stale_after_sec must be positive')
        if reconnect_ms <= 0:
            raise ValueError('reconnect_ms must be positive')
        self.source_type = source_type
        self.topic_name = topic_name
        self.device_index = int(device_index)
        self.stale_after_sec = float(stale_after_sec)
        self.health = CameraHealthMonitor(expected_fps=expected_fps, reconnect_ms=int(reconnect_ms))
        self.publisher = FramePublisher()
        self.mock_profile = str(mock_profile or DEFAULT_MOCK_PROFILE)
        self._source = MockCameraSource(mock_profile=self.mock_profile) if source_type == 'mock' else TopicCameraSource()
        if self.source_type == 'mock':
            self.health.device_opened()

    def receive_frame(self, frame: CaptureFrame, *, now: float | None = None) -> dict[str, Any]:
        """Accept an external frame and update camera health.

        Args:
            frame: Incoming capture frame.
            now: Optional monotonic timestamp.

        Returns:
            dict[str, Any]: Enriched frame summary.

        Raises:
            ValueError: If ``frame`` is invalid.
        """
        if not isinstance(frame, CaptureFrame):
            raise ValueError('frame must be a CaptureFrame instance')
        timestamp = time.monotonic() if now is None else now
        if isinstance(self._source, TopicCameraSource):
            self._source.update(frame, received_monotonic=timestamp)
        self.health.device_opened()
        self.health.frame_received(timestamp)
        return {
            **self.publisher.to_summary(frame, timestamp_sec=time.time(), source_metadata=self._source_metadata()),
            'health': self.health.snapshot(timestamp, stale_after_sec=self.stale_after_sec),
        }

    def capture_once(self) -> dict[str, Any]:
        """Capture or fetch one frame and return an enriched summary.

        Args:
            None.

        Returns:
            dict[str, Any]: Enriched frame summary.

        Raises:
            RuntimeError: If the configured source cannot provide a frame.
        """
        try:
            frame = self._source.read_frame()
        except Exception as exc:
            self.health.frame_dropped()
            self.health.reconnect_attempted()
            self.health.device_closed()
            raise RuntimeError(str(exc)) from exc
        return self.receive_frame(frame)

    def health_snapshot(self, *, now: float | None = None) -> dict[str, Any]:
        """Return the current camera-health snapshot.

        Args:
            now: Optional monotonic timestamp.

        Returns:
            dict[str, Any]: Camera-health snapshot.

        Raises:
            Does not raise.
        """
        timestamp = time.monotonic() if now is None else now
        return self.health.snapshot(timestamp, stale_after_sec=self.stale_after_sec)

    def _source_metadata(self) -> dict[str, Any]:
        """Return source metadata for frame summaries.

        Args:
            None.

        Returns:
            dict[str, Any]: Source metadata.

        Raises:
            Does not raise.
        """
        return {'sourceType': self.source_type, 'topicName': self.topic_name, 'deviceIndex': self.device_index, 'mockProfile': self.mock_profile if self.source_type == 'mock' else ''}


def main(args=None) -> None:
    _ = args
    node = CameraDriverNode()
    node.capture_once()
