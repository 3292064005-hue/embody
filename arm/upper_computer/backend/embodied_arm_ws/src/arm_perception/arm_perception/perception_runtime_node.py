from __future__ import annotations

import json
import time
from typing import Any

from std_msgs.msg import String

from arm_backend_common.lifecycle_support import ManagedLifecycleNode, lifecycle_main
from arm_common import MsgTypes, TopicNames, build_target_array_message
from .perception_node import PerceptionNode

TargetArray = MsgTypes.TargetArray
TargetInfo = MsgTypes.TargetInfo


class PerceptionRuntimeNode(ManagedLifecycleNode):
    """Lifecycle runtime node that converts camera frames into authoritative targets."""

    def __init__(self) -> None:
        super().__init__('perception_node')
        self.declare_parameter('stale_after_sec', 2.0)
        self.declare_parameter('min_seen_count', 1)
        self.declare_parameter('input_topic', TopicNames.CAMERA_FRAME_SUMMARY)
        self.declare_parameter('status_period_sec', 0.5)
        self._stale_after_sec = float(self.get_parameter('stale_after_sec').value)
        self._runtime = PerceptionNode(
            stale_after_sec=self._stale_after_sec,
            min_seen_count=int(self.get_parameter('min_seen_count').value),
        )
        self._summary_pub = self.create_managed_publisher(String, TopicNames.VISION_SUMMARY, 10)
        self._targets_pub = self.create_managed_publisher(String, TopicNames.VISION_TARGETS, 10)
        self._targets_typed_pub = self.create_managed_publisher(TargetArray, TopicNames.VISION_TARGETS_TYPED, 10) if TargetArray is not object else None
        self._target_pub = self.create_managed_publisher(TargetInfo, TopicNames.VISION_TARGET, 10)
        self._readiness_pub = self.create_managed_publisher(String, TopicNames.READINESS_UPDATE, 10)
        self._last_processed_summary: dict[str, Any] | None = None
        self._last_error: str | None = None
        self.create_subscription(String, str(self.get_parameter('input_topic').value), self._on_frame_summary, 20)
        self.create_timer(float(self.get_parameter('status_period_sec').value), self._publish_status)

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

    def _decode_frame_payload(self, raw: str) -> Any:
        """Decode the runtime camera-frame summary payload.

        Args:
            raw: JSON-encoded frame summary.

        Returns:
            Any: Frame payload forwarded to perception processors.

        Raises:
            ValueError: If the frame summary cannot be decoded.
        """
        try:
            payload = json.loads(raw) if raw else {}
        except Exception as exc:
            raise ValueError(f'invalid frame summary json: {exc}') from exc
        if not isinstance(payload, dict):
            raise ValueError('frame summary payload must decode to a dict')
        frame = payload.get('frame', payload)
        if not isinstance(frame, dict):
            raise ValueError('frame summary missing frame object')
        return frame.get('payload', frame)

    def _publish_primary_target(self, target: dict[str, Any] | None) -> None:
        if not target:
            return
        msg = TargetInfo()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.target_id = str(target.get('target_id', ''))
        msg.target_type = str(target.get('target_type', target.get('type', 'unknown')))
        msg.semantic_label = str(target.get('semantic_label', target.get('label', msg.target_type)))
        msg.image_u = float(target.get('image_u', target.get('u', 0.0)))
        msg.image_v = float(target.get('image_v', target.get('v', 0.0)))
        msg.table_x = float(target.get('table_x', target.get('x', 0.0)))
        msg.table_y = float(target.get('table_y', target.get('y', 0.0)))
        msg.yaw = float(target.get('yaw', 0.0))
        msg.confidence = float(target.get('confidence', 0.0))
        msg.is_valid = bool(target.get('is_valid', msg.confidence >= 0.5))
        self._target_pub.publish(msg)

    def _publish_targets_summary(self, summary: dict[str, Any]) -> None:
        targets = list(summary.get('targets') or [])
        payload = {
            'source': 'perception_runtime',
            'targets': targets,
            'targetCount': len(targets),
            'primaryTarget': summary.get('primaryTarget'),
            'processedAtMonotonic': summary.get('processedAtMonotonic'),
        }
        self._targets_pub.publish(String(data=json.dumps(payload, ensure_ascii=False)))
        if self._targets_typed_pub is not None:
            self._targets_typed_pub.publish(build_target_array_message(payload, stamp_factory=lambda: self.get_clock().now().to_msg()))

    def _publish_processing_outputs(self, summary: dict[str, Any]) -> None:
        self._last_processed_summary = dict(summary)
        self._last_error = None
        self._summary_pub.publish(String(data=json.dumps({'source': 'perception_runtime', **summary}, ensure_ascii=False)))
        self._publish_targets_summary(summary)
        self._publish_primary_target(summary.get('primaryTarget'))
        perception_alive = bool(summary.get('perceptionAlive', False))
        target_available = bool(summary.get('targetAvailable', False))
        self._publish_readiness_update('perception_alive', perception_alive, 'perception_streaming' if perception_alive else 'perception_stale')
        self._publish_readiness_update('target_available', target_available, 'target_available' if target_available else 'target_unavailable')

    def _on_frame_summary(self, msg: String) -> None:
        """Consume one authoritative camera frame summary and execute perception.

        Args:
            msg: Serialized camera-frame summary.

        Returns:
            None.

        Raises:
            Does not raise. Decoder or processor failures are converted into
            readiness degradation and stored in ``_last_error``.
        """
        if not self.runtime_active:
            return
        try:
            frame_payload = self._decode_frame_payload(msg.data)
            summary = self._runtime.receive_frame(frame_payload, now=time.monotonic())
        except Exception as exc:
            self._last_error = str(exc)
            self._publish_readiness_update('perception_alive', False, 'perception_error')
            self._publish_readiness_update('target_available', False, 'target_unavailable')
            return
        self._publish_processing_outputs(summary)

    def _publish_status(self) -> None:
        if not self.runtime_active:
            return
        health = self._runtime.health_snapshot(now=time.monotonic(), stale_after_sec=self._stale_after_sec)
        payload = {
            'source': 'perception_runtime',
            'perception': health,
            'targets': self._runtime.current_targets(now=time.monotonic()),
            'primaryTarget': health.get('primaryTarget'),
            'lastSummary': self._last_processed_summary,
            'lastError': self._last_error,
        }
        self._summary_pub.publish(String(data=json.dumps(payload, ensure_ascii=False)))
        perception_alive = bool(health.get('perceptionAlive', False))
        target_available = bool(health.get('targetAvailable', False))
        self._publish_readiness_update('perception_alive', perception_alive, 'perception_streaming' if perception_alive else 'perception_stale')
        self._publish_readiness_update('target_available', target_available, 'target_available' if target_available else 'target_unavailable')



def main(args=None) -> None:
    lifecycle_main(PerceptionRuntimeNode, args=args)
