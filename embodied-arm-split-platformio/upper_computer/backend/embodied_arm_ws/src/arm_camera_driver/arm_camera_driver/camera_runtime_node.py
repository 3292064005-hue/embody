from __future__ import annotations

import json
import time
from typing import Any

from std_msgs.msg import String

from arm_backend_common.lifecycle_support import ManagedLifecycleNode, lifecycle_main
from arm_common import TopicNames
from .camera_node import CameraDriverNode
from .capture_backend import CaptureFrame


class CameraRuntimeNode(ManagedLifecycleNode):
    """Lifecycle runtime node that drives camera capture and publishes frame freshness.

    The node owns runtime orchestration only. Frame acquisition and health accounting
    remain delegated to :class:`CameraDriverNode`.
    """

    def __init__(self) -> None:
        super().__init__('camera_driver_node')
        self.declare_parameter('source_type', 'mock')
        self.declare_parameter('topic_name', TopicNames.CAMERA_IMAGE)
        self.declare_parameter('frame_topic', TopicNames.CAMERA_FRAME_SUMMARY)
        self.declare_parameter('device_index', 0)
        self.declare_parameter('expected_fps', 15.0)
        self.declare_parameter('stale_after_sec', 1.0)
        self.declare_parameter('reconnect_ms', 2000)
        self.declare_parameter('capture_period_sec', 0.2)
        self.declare_parameter('status_period_sec', 0.5)
        self._source_type = str(self.get_parameter('source_type').value)
        self._frame_topic = str(self.get_parameter('frame_topic').value)
        self._stale_after_sec = float(self.get_parameter('stale_after_sec').value)
        self._driver = CameraDriverNode(
            source_type=self._source_type,
            topic_name=str(self.get_parameter('topic_name').value),
            device_index=int(self.get_parameter('device_index').value),
            expected_fps=float(self.get_parameter('expected_fps').value),
            stale_after_sec=self._stale_after_sec,
            reconnect_ms=int(self.get_parameter('reconnect_ms').value),
        )
        self._last_frame_summary: dict[str, Any] | None = None
        self._last_capture_error: str | None = None
        self._frame_pub = self.create_managed_publisher(String, self._frame_topic, 10)
        self._summary_pub = self.create_managed_publisher(String, TopicNames.CAMERA_HEALTH_SUMMARY, 10)
        self._readiness_pub = self.create_managed_publisher(String, TopicNames.READINESS_UPDATE, 10)
        if self._source_type == 'topic':
            self.create_subscription(String, str(self.get_parameter('topic_name').value), self._on_external_frame, 20)
        else:
            self.create_timer(float(self.get_parameter('capture_period_sec').value), self._capture_once)
        self.create_timer(float(self.get_parameter('status_period_sec').value), self._publish_status)

    def _decode_external_frame(self, raw: str) -> CaptureFrame:
        """Decode one externally supplied frame payload.

        Args:
            raw: JSON payload received on the external camera topic.

        Returns:
            CaptureFrame: Parsed capture frame.

        Raises:
            ValueError: If the payload cannot be decoded into a valid frame.
        """
        try:
            payload = json.loads(raw) if raw else {}
        except Exception as exc:
            raise ValueError(f'invalid camera frame json: {exc}') from exc
        if isinstance(payload, dict) and isinstance(payload.get('frame'), dict):
            payload = payload['frame']
        if isinstance(payload, list):
            payload = {'payload': payload}
        if not isinstance(payload, dict):
            raise ValueError('external frame payload must decode to a dict or list')
        width = int(payload.get('width', 640) or 640)
        height = int(payload.get('height', 480) or 480)
        frame_id = str(payload.get('frame_id', payload.get('frameId', 'camera_optical_frame')) or 'camera_optical_frame')
        frame_payload = payload.get('payload')
        if frame_payload is None:
            raise ValueError('external frame payload missing payload field')
        return CaptureFrame(width=width, height=height, frame_id=frame_id, payload=frame_payload)

    def _publish_readiness_update(self, check: str, ok: bool, detail: str) -> None:
        self._readiness_pub.publish(
            String(
                data=json.dumps(
                    {
                        'check': check,
                        'ok': bool(ok),
                        'detail': str(detail),
                        'staleAfterSec': self._stale_after_sec,
                    },
                    ensure_ascii=False,
                )
            )
        )

    def _publish_frame_summary(self, summary: dict[str, Any]) -> None:
        self._last_frame_summary = dict(summary)
        self._last_capture_error = None
        payload = {
            'source': 'camera_runtime',
            'frame': dict(summary),
            'capturedAt': time.time(),
        }
        self._frame_pub.publish(String(data=json.dumps(payload, ensure_ascii=False)))

    def _capture_once(self) -> None:
        """Capture one frame from the configured source and publish it.

        Boundary behavior:
            Capture failures are converted into readiness degradation and retained as
            structured status in ``_last_capture_error``. The timer never raises.
        """
        if not self.runtime_active:
            return
        try:
            summary = self._driver.capture_once()
        except Exception as exc:
            self._last_capture_error = str(exc)
            self._publish_readiness_update('camera', False, 'capture_error')
            self._publish_readiness_update('camera_alive', False, 'capture_error')
            return
        self._publish_frame_summary(summary)
        self._publish_readiness_update('camera', True, 'frame_captured')
        self._publish_readiness_update('camera_alive', True, 'camera_streaming')

    def _on_external_frame(self, msg: String) -> None:
        """Receive one externally published frame and convert it to the runtime contract.

        Args:
            msg: Serialized JSON payload carrying a frame or raw frame payload.

        Returns:
            None.

        Raises:
            Does not raise. Parse errors are converted into readiness degradation.
        """
        if not self.runtime_active:
            return
        try:
            frame = self._decode_external_frame(msg.data)
            summary = self._driver.receive_frame(frame)
        except Exception as exc:
            self._last_capture_error = str(exc)
            self._publish_readiness_update('camera', False, 'frame_parse_error')
            self._publish_readiness_update('camera_alive', False, 'frame_parse_error')
            return
        self._publish_frame_summary(summary)
        self._publish_readiness_update('camera', True, 'frame_received')
        self._publish_readiness_update('camera_alive', True, 'camera_streaming')

    def _publish_status(self) -> None:
        if not self.runtime_active:
            return
        health = self._driver.health_snapshot(now=time.monotonic())
        camera_alive = bool(health.get('cameraAlive', False))
        detail = 'camera_streaming' if camera_alive else ('capture_error' if self._last_capture_error else 'camera_stale')
        self._summary_pub.publish(
            String(
                data=json.dumps(
                    {
                        'source': 'camera_runtime',
                        'camera': health,
                        'lastFrame': self._last_frame_summary,
                        'lastError': self._last_capture_error,
                    },
                    ensure_ascii=False,
                )
            )
        )
        self._publish_readiness_update('camera', camera_alive, detail)
        self._publish_readiness_update('camera_alive', camera_alive, detail)



def main(args=None) -> None:
    lifecycle_main(CameraRuntimeNode, args=args)
