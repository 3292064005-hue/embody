from __future__ import annotations

import json
from typing import Any

try:
    import rclpy
    from arm_backend_common.lifecycle_support import ManagedLifecycleNode, lifecycle_main, ros_io_enabled
    from std_msgs.msg import String
    from arm_common import ServiceNames, SrvTypes, TopicNames
except Exception:  # pragma: no cover
    rclpy = None
    ManagedLifecycleNode = object

    def lifecycle_main(factory, args=None):
        del factory, args
        raise RuntimeError('rclpy unavailable')

    def ros_io_enabled(*, enable_ros_io: bool, message_cls=None):
        del message_cls
        return False

    String = object

    class TopicNames:
        INTERNAL_SELECTED_TARGET = '/arm/internal/selected_target'
        INTERNAL_SYNC_SCENE = '/arm/internal/sync_scene'
        SCENE_SUMMARY = '/arm/scene/summary'
        READINESS_UPDATE = '/arm/readiness/update'

    class ServiceNames:
        RUNTIME_SCENE_SNAPSHOT = '/arm/internal/runtime_scene_snapshot'

    class _SrvTypes:
        RuntimeSceneSnapshot = object

    SrvTypes = _SrvTypes()

from arm_backend_common import (
    LOCAL_RUNTIME_SERVICE_REGISTRY,
    build_runtime_service_response,
    decode_runtime_service_payload,
    encode_runtime_service_payload,
)

from .scene_service import SceneService


class SceneManagerNode(ManagedLifecycleNode):
    """Runtime scene-manager node wrapping the pure :class:`SceneService`.

    Boundary behavior:
        - Registers a process-local runtime-service fallback for pure-Python tests.
        - Exposes the ROS runtime-service endpoint when the interface package is
          available.
        - Publishes a dedicated readiness check so task gating can fail closed
          when the runtime scene-service boundary is unavailable.
    """

    READINESS_CHECK = 'scene_runtime_service'
    READINESS_STALE_AFTER_SEC = 2.5

    def __init__(self, *, enable_ros_io: bool = True, service: SceneService | None = None) -> None:
        self._ros_enabled = ros_io_enabled(enable_ros_io=enable_ros_io, message_cls=String)
        if self._ros_enabled:
            super().__init__('scene_manager')
        self._service = service or SceneService(provider_mode='runtime_service', authoritative=True, source_authority='runtime_service')
        self._summary_pub = self.create_managed_publisher(String, TopicNames.SCENE_SUMMARY, 10) if self._ros_enabled else None
        self._readiness_pub = self.create_managed_publisher(String, TopicNames.READINESS_UPDATE, 10) if self._ros_enabled else None
        self._runtime_scene_srv_type = getattr(SrvTypes, 'RuntimeSceneSnapshot', object)
        self._runtime_scene_service_created = False
        if self._ros_enabled:
            self.create_subscription(String, TopicNames.INTERNAL_SELECTED_TARGET, self._on_selected_target, 20)
            self.create_subscription(String, TopicNames.INTERNAL_SYNC_SCENE, self._on_sync_scene, 20)
            if self._runtime_scene_srv_type is not object:
                self.create_service(self._runtime_scene_srv_type, ServiceNames.RUNTIME_SCENE_SNAPSHOT, self._handle_runtime_scene_snapshot)
                self._runtime_scene_service_created = True
            self.create_timer(self.READINESS_STALE_AFTER_SEC / 2.0, self._publish_readiness)
        self._runtime_service_handler = self._dispatch_runtime_scene_snapshot
        LOCAL_RUNTIME_SERVICE_REGISTRY.register(ServiceNames.RUNTIME_SCENE_SNAPSHOT, self._runtime_service_handler)

    @property
    def static_scene(self):
        return self._service.static_scene

    @property
    def target_builder(self):
        return self._service.target_builder

    @property
    def attachments(self):
        return self._service.attachments

    def update_target(self, target: dict[str, Any] | None) -> dict[str, Any]:
        snapshot = self._service.update_target(target)
        self._publish_snapshot(snapshot)
        return snapshot

    def attach_target(self, target_id: str, *, link_name: str = 'tool0', metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        result = self._service.attach_target(target_id, link_name=link_name, metadata=metadata)
        self._publish_snapshot(self._service.current_scene())
        return result

    def detach_target(self, target_id: str) -> dict[str, Any]:
        result = self._service.detach_target(target_id)
        self._publish_snapshot(self._service.current_scene())
        return result

    def sync_scene(self, payload: dict[str, Any]) -> dict[str, Any]:
        snapshot = self._service.sync_scene(payload)
        self._publish_snapshot(snapshot)
        return snapshot

    def build_scene_snapshot(self, target: dict[str, Any] | None = None) -> dict[str, Any]:
        return self._service.build_scene_snapshot(target)

    def current_scene(self) -> dict[str, Any]:
        return self._service.current_scene()

    def destroy_node(self):  # pragma: no cover - depends on ROS lifecycle shutdown
        LOCAL_RUNTIME_SERVICE_REGISTRY.unregister(ServiceNames.RUNTIME_SCENE_SNAPSHOT, getattr(self, '_runtime_service_handler', None))
        base_destroy = getattr(super(), 'destroy_node', None)
        if callable(base_destroy):
            return base_destroy()
        return None

    def _publish_snapshot(self, snapshot: dict[str, Any]) -> None:
        if self._ros_enabled and not self.runtime_active:
            return
        if self._summary_pub is None or String is object:
            return
        self._summary_pub.publish(String(data=json.dumps(snapshot, ensure_ascii=False)))

    def _runtime_boundary_status(self) -> tuple[bool, str]:
        if self._ros_enabled:
            if self._runtime_scene_srv_type is object:
                return False, 'scene_runtime_service_interface_unavailable'
            if not self._runtime_scene_service_created:
                return False, 'scene_runtime_service_not_created'
            return True, 'scene_runtime_service_ready'
        if LOCAL_RUNTIME_SERVICE_REGISTRY.contains(ServiceNames.RUNTIME_SCENE_SNAPSHOT):
            return True, 'local_runtime_service_ready'
        return False, 'scene_runtime_service_unavailable'

    def _publish_readiness(self) -> None:
        if self._readiness_pub is None or String is object:
            return
        if self._ros_enabled and not self.runtime_active:
            return
        ok, detail = self._runtime_boundary_status()
        self._readiness_pub.publish(String(data=json.dumps({'check': self.READINESS_CHECK, 'ok': bool(ok), 'detail': detail, 'staleAfterSec': self.READINESS_STALE_AFTER_SEC}, ensure_ascii=False)))

    def _dispatch_runtime_scene_snapshot(self, request: dict[str, Any]):
        try:
            if not isinstance(request, dict):
                raise ValueError('request must be a dictionary')
            if 'scene' in request:
                snapshot = self.sync_scene(dict(request.get('scene') or {}))
            else:
                target = request.get('target')
                snapshot = self.update_target(dict(target) if isinstance(target, dict) else None)
            return build_runtime_service_response(payload=snapshot)
        except Exception as exc:
            return build_runtime_service_response(error=str(exc))

    def _handle_runtime_scene_snapshot(self, request: Any, response: Any) -> Any:
        envelope = self._dispatch_runtime_scene_snapshot(decode_runtime_service_payload(getattr(request, 'request_json', ''), field_name='scene request_json'))
        response.ok = bool(envelope.ok)
        response.error = str(envelope.error)
        response.snapshot_json = encode_runtime_service_payload(envelope.payload)
        return response

    def _on_selected_target(self, msg: String) -> None:
        if self._ros_enabled and not self.runtime_active:
            return
        payload = self._parse_json(msg.data)
        target = payload.get('target') if 'target' in payload else payload
        self.update_target(target or None)

    def _on_sync_scene(self, msg: String) -> None:
        if self._ros_enabled and not self.runtime_active:
            return
        payload = self._parse_json(msg.data)
        if payload:
            self.sync_scene(payload)

    @staticmethod
    def _parse_json(payload: str) -> dict[str, Any]:
        if not payload:
            return {}
        try:
            parsed = json.loads(payload)
        except Exception:
            return {}
        return parsed if isinstance(parsed, dict) else {}


def main(args=None) -> None:
    if rclpy is None:
        SceneManagerNode(enable_ros_io=False)
        return
    lifecycle_main(SceneManagerNode, args=args)
