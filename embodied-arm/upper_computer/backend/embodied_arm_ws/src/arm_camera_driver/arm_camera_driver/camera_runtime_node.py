from __future__ import annotations

import json
import time
from typing import Any

try:  # pragma: no cover - exercised in ROS runtime.
    from std_msgs.msg import String
    from sensor_msgs.msg import CameraInfo, Image
except Exception:  # pragma: no cover - import fallback for pure-python tests.
    class String:  # type: ignore[override]
        def __init__(self, data: str = '') -> None:
            self.data = data

    CameraInfo = object  # type: ignore[assignment]
    Image = object  # type: ignore[assignment]

from arm_backend_common.lifecycle_support import ManagedLifecycleNode, lifecycle_main
from arm_common import TopicNames
from .camera_node import CameraDriverNode
from .capture_backend import CaptureFrame


class CameraRuntimeNode(ManagedLifecycleNode):
    """Lifecycle runtime node that drives camera capture and publishes frame freshness.

    The node owns runtime orchestration only. Frame acquisition and health accounting
    remain delegated to :class:`CameraDriverNode`. Standard ROS image ingress is the
    primary contract exposed through :class:`arm_common.TopicNames`. The historic JSON
    ingress remains available through the compatibility topic constant for migrations.
    """

    def __init__(self) -> None:
        super().__init__('camera_driver_node')
        self.declare_parameter('source_type', 'mock')
        self.declare_parameter('topic_name', TopicNames.CAMERA_IMAGE_RAW)
        self.declare_parameter('legacy_topic_name', TopicNames.CAMERA_IMAGE_COMPAT)
        self.declare_parameter('frame_topic', TopicNames.CAMERA_FRAME_SUMMARY)
        self.declare_parameter('camera_info_topic', TopicNames.CAMERA_INFO)
        self.declare_parameter('device_index', 0)
        self.declare_parameter('expected_fps', 15.0)
        self.declare_parameter('stale_after_sec', 1.0)
        self.declare_parameter('reconnect_ms', 2000)
        self.declare_parameter('capture_period_sec', 0.2)
        self.declare_parameter('status_period_sec', 0.5)
        self.declare_parameter('mock_profile', 'authoritative_demo')
        self.declare_parameter('frame_ingress_mode', 'reserved_endpoint')
        self.declare_parameter('publish_standard_image', True)
        self.declare_parameter('republish_compat_frames_as_standard_image', False)
        self._source_type = str(self.get_parameter('source_type').value)
        self._frame_topic = str(self.get_parameter('frame_topic').value)
        self._stale_after_sec = float(self.get_parameter('stale_after_sec').value)
        self._frame_ingress_mode = str(self.get_parameter('frame_ingress_mode').value)
        self._publish_standard_image = bool(self.get_parameter('publish_standard_image').value)
        self._republish_compat_frames_as_standard_image = bool(self.get_parameter('republish_compat_frames_as_standard_image').value)
        self._driver = CameraDriverNode(
            source_type=self._source_type,
            topic_name=str(self.get_parameter('topic_name').value),
            device_index=int(self.get_parameter('device_index').value),
            expected_fps=float(self.get_parameter('expected_fps').value),
            stale_after_sec=self._stale_after_sec,
            reconnect_ms=int(self.get_parameter('reconnect_ms').value),
            mock_profile=str(self.get_parameter('mock_profile').value),
        )
        self._last_frame_summary: dict[str, Any] | None = None
        self._last_capture_error: str | None = None
        self._frame_pub = self.create_managed_publisher(String, self._frame_topic, 10)
        self._summary_pub = self.create_managed_publisher(String, TopicNames.CAMERA_HEALTH_SUMMARY, 10)
        self._readiness_pub = self.create_managed_publisher(String, TopicNames.READINESS_UPDATE, 10)
        self._image_pub = self.create_managed_publisher(Image, TopicNames.CAMERA_IMAGE_RAW, 10) if Image is not object else None
        self._camera_info_pub = self.create_managed_publisher(CameraInfo, TopicNames.CAMERA_INFO, 10) if CameraInfo is not object else None
        if self._source_type == 'topic':
            if Image is not object:
                self.create_subscription(Image, str(self.get_parameter('topic_name').value), self._on_external_image, 20)
            self.create_subscription(String, str(self.get_parameter('legacy_topic_name').value), self._on_external_frame, 20)
        else:
            self.create_timer(float(self.get_parameter('capture_period_sec').value), self._capture_once)
        self.create_timer(float(self.get_parameter('status_period_sec').value), self._publish_status)


    def _should_publish_standard_image(self, *, source: str) -> bool:
        """Return whether one ingress source may emit standard ROS image messages.

        Args:
            source: Stable ingress source token such as ``capture`` or ``compat``.

        Returns:
            bool: ``True`` when the current source is allowed to publish a standard
                ``sensor_msgs/Image`` representation.

        Raises:
            Does not raise. Unknown sources fail closed.
        """
        if not self._publish_standard_image:
            return False
        if source == 'capture':
            return True
        if source == 'compat':
            return bool(self._republish_compat_frames_as_standard_image)
        return False

    def _decode_external_frame(self, raw: str) -> CaptureFrame:
        """Decode one externally supplied compatibility frame payload.

        Args:
            raw: JSON payload received on the legacy camera topic.

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

    def _decode_image_message(self, msg: Image) -> CaptureFrame:
        """Convert a standard ROS image message into the internal capture contract.

        Args:
            msg: ``sensor_msgs/Image`` payload from the standard ingress topic.

        Returns:
            CaptureFrame: Structured capture frame carrying image metadata.

        Raises:
            ValueError: If the message payload is invalid.
        """
        width = int(getattr(msg, 'width', 0) or 0)
        height = int(getattr(msg, 'height', 0) or 0)
        if width <= 0 or height <= 0:
            raise ValueError('image_raw message must include positive width and height')
        frame_id = str(getattr(getattr(msg, 'header', None), 'frame_id', '') or 'camera_optical_frame')
        payload = {
            'kind': 'sensor_image',
            'encoding': str(getattr(msg, 'encoding', '') or 'mono8'),
            'step': int(getattr(msg, 'step', 0) or 0),
            'dataSize': len(getattr(msg, 'data', b'') or b''),
            'targets': [],
        }
        return CaptureFrame(width=width, height=height, frame_id=frame_id, payload=payload)

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

    def _blank_image_data(self, *, width: int, height: int) -> bytes:
        pixel_count = max(int(width), 1) * max(int(height), 1)
        return bytes(pixel_count)

    def _publish_standard_image_from_summary(self, summary: dict[str, Any]) -> None:
        """Publish standard ROS image/camera-info messages derived from a frame summary.

        Args:
            summary: Runtime frame summary produced by the camera driver.

        Returns:
            None.

        Raises:
            Does not raise. Missing ROS message types degrade to a no-op.
        """
        if not self._publish_standard_image or self._image_pub is None:
            return
        width = int(summary.get('width', 640) or 640)
        height = int(summary.get('height', 480) or 480)
        frame_id = str(summary.get('frame_id', summary.get('frameId', 'camera_optical_frame')) or 'camera_optical_frame')
        image = Image()
        image.header.stamp = self.get_clock().now().to_msg()
        image.header.frame_id = frame_id
        image.height = height
        image.width = width
        image.encoding = 'mono8'
        image.is_bigendian = 0
        image.step = width
        image.data = self._blank_image_data(width=width, height=height)
        self._image_pub.publish(image)
        if self._camera_info_pub is not None:
            camera_info = CameraInfo()
            camera_info.header.stamp = image.header.stamp
            camera_info.header.frame_id = frame_id
            camera_info.height = height
            camera_info.width = width
            self._camera_info_pub.publish(camera_info)

    def _publish_frame_summary(self, summary: dict[str, Any], *, publish_standard_image: bool) -> None:
        self._last_frame_summary = dict(summary)
        self._last_capture_error = None
        payload = {
            'source': 'camera_runtime',
            'frameIngressMode': self._frame_ingress_mode,
            'frame': dict(summary),
            'capturedAt': time.time(),
        }
        self._frame_pub.publish(String(data=json.dumps(payload, ensure_ascii=False)))
        if publish_standard_image:
            self._publish_standard_image_from_summary(summary)

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
        self._publish_frame_summary(summary, publish_standard_image=self._should_publish_standard_image(source='capture'))
        self._publish_readiness_update('camera', True, 'frame_captured')
        self._publish_readiness_update('camera_alive', True, 'camera_streaming')

    def _on_external_frame(self, msg: String) -> None:
        """Receive one compatibility JSON frame and convert it to the runtime contract.

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
        self._publish_frame_summary(summary, publish_standard_image=self._should_publish_standard_image(source='compat'))
        self._publish_readiness_update('camera', True, 'frame_received')
        self._publish_readiness_update('camera_alive', True, 'camera_streaming')

    def _on_external_image(self, msg: Image) -> None:
        """Consume one standard ROS image without re-publishing it onto the same topic.

        Args:
            msg: ``sensor_msgs/Image`` payload from the standard ingress topic.

        Returns:
            None.

        Raises:
            Does not raise. Decode failures are converted into readiness degradation.
        """
        if not self.runtime_active:
            return
        try:
            frame = self._decode_image_message(msg)
            summary = self._driver.receive_frame(frame)
        except Exception as exc:
            self._last_capture_error = str(exc)
            self._publish_readiness_update('camera', False, 'frame_parse_error')
            self._publish_readiness_update('camera_alive', False, 'frame_parse_error')
            return
        self._publish_frame_summary(summary, publish_standard_image=False)
        self._publish_readiness_update('camera', True, 'image_raw_received')
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
                        'frameIngressMode': self._frame_ingress_mode,
                        'standardImageTopic': TopicNames.CAMERA_IMAGE_RAW,
                        'legacyCompatTopic': TopicNames.CAMERA_IMAGE_COMPAT,
                        'compatRepublishStandardImage': bool(self._republish_compat_frames_as_standard_image),
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
