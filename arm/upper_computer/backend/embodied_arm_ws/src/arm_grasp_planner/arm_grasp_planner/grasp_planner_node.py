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
        INTERNAL_GENERATE_GRASPS = '/arm/internal/generate_grasps'
        GRASP_PLAN_SUMMARY = '/arm/grasp/summary'
        READINESS_UPDATE = '/arm/readiness/update'

    class ServiceNames:
        RUNTIME_GRASP_PLAN = '/arm/internal/runtime_grasp_plan'

    class _SrvTypes:
        RuntimeGraspPlan = object

    SrvTypes = _SrvTypes()

from arm_backend_common import (
    LOCAL_RUNTIME_SERVICE_REGISTRY,
    build_runtime_service_response,
    decode_runtime_service_payload,
    encode_runtime_service_payload,
)
from arm_backend_common.data_models import TargetSnapshot

from .grasp_service import GraspPlanningService


class GraspPlannerNode(ManagedLifecycleNode):
    """Runtime grasp-planner node wrapping the pure :class:`GraspPlanningService`.

    Boundary behavior:
        - Registers a process-local runtime-service fallback for pure-Python tests.
        - Exposes the ROS runtime-service endpoint when the interface package is
          available.
        - Publishes a dedicated readiness check so task gating can fail closed
          when the runtime grasp-service boundary is unavailable.
    """

    READINESS_CHECK = 'grasp_runtime_service'
    READINESS_STALE_AFTER_SEC = 2.5

    def __init__(self, *, enable_ros_io: bool = True, service: GraspPlanningService | None = None) -> None:
        self._ros_enabled = ros_io_enabled(enable_ros_io=enable_ros_io, message_cls=String)
        if self._ros_enabled:
            super().__init__('grasp_planner')
        self._service = service or GraspPlanningService(provider_mode='runtime_service', authoritative=True, source_authority='runtime_service')
        self._summary_pub = self.create_managed_publisher(String, TopicNames.GRASP_PLAN_SUMMARY, 10) if self._ros_enabled else None
        self._readiness_pub = self.create_managed_publisher(String, TopicNames.READINESS_UPDATE, 10) if self._ros_enabled else None
        self._runtime_grasp_srv_type = getattr(SrvTypes, 'RuntimeGraspPlan', object)
        self._runtime_grasp_service_created = False
        if self._ros_enabled:
            self.create_subscription(String, TopicNames.INTERNAL_GENERATE_GRASPS, self._on_generate_grasps, 20)
            if self._runtime_grasp_srv_type is not object:
                self.create_service(self._runtime_grasp_srv_type, ServiceNames.RUNTIME_GRASP_PLAN, self._handle_runtime_grasp_plan)
                self._runtime_grasp_service_created = True
            self.create_timer(self.READINESS_STALE_AFTER_SEC / 2.0, self._publish_readiness)
        self._runtime_service_handler = self._dispatch_runtime_grasp_plan
        LOCAL_RUNTIME_SERVICE_REGISTRY.register(ServiceNames.RUNTIME_GRASP_PLAN, self._runtime_service_handler)

    @property
    def generator(self):
        return self._service.generator

    @property
    def ranker(self):
        return self._service.ranker

    @property
    def pregrasp(self):
        return self._service.pregrasp

    @property
    def place_pose(self):
        return self._service.place_pose

    @property
    def fallback(self):
        return self._service.fallback

    def plan(self, target: TargetSnapshot | dict[str, Any], place_zone: dict[str, Any] | None = None, *, failed_ids: list[str] | None = None) -> dict[str, Any]:
        plan = self._service.plan(target, place_zone, failed_ids=failed_ids)
        self._publish_plan(plan)
        return plan

    def last_plan(self) -> dict[str, Any]:
        return self._service.last_plan()

    def destroy_node(self):  # pragma: no cover - depends on ROS lifecycle shutdown
        LOCAL_RUNTIME_SERVICE_REGISTRY.unregister(ServiceNames.RUNTIME_GRASP_PLAN, getattr(self, '_runtime_service_handler', None))
        base_destroy = getattr(super(), 'destroy_node', None)
        if callable(base_destroy):
            return base_destroy()
        return None

    def _publish_plan(self, plan: dict[str, Any]) -> None:
        if self._ros_enabled and not self.runtime_active:
            return
        if self._summary_pub is None or String is object:
            return
        self._summary_pub.publish(String(data=json.dumps(plan, ensure_ascii=False)))

    def _runtime_boundary_status(self) -> tuple[bool, str]:
        if self._ros_enabled:
            if self._runtime_grasp_srv_type is object:
                return False, 'grasp_runtime_service_interface_unavailable'
            if not self._runtime_grasp_service_created:
                return False, 'grasp_runtime_service_not_created'
            return True, 'grasp_runtime_service_ready'
        if LOCAL_RUNTIME_SERVICE_REGISTRY.contains(ServiceNames.RUNTIME_GRASP_PLAN):
            return True, 'local_runtime_service_ready'
        return False, 'grasp_runtime_service_unavailable'

    def _publish_readiness(self) -> None:
        if self._readiness_pub is None or String is object:
            return
        if self._ros_enabled and not self.runtime_active:
            return
        ok, detail = self._runtime_boundary_status()
        self._readiness_pub.publish(String(data=json.dumps({'check': self.READINESS_CHECK, 'ok': bool(ok), 'detail': detail, 'staleAfterSec': self.READINESS_STALE_AFTER_SEC}, ensure_ascii=False)))

    def _dispatch_runtime_grasp_plan(self, request: dict[str, Any]):
        try:
            if not isinstance(request, dict):
                raise ValueError('request must be a dictionary')
            target = request.get('target') or {}
            place = request.get('place') or {}
            failed_ids = list(request.get('failedIds') or [])
            plan = self.plan(target, place, failed_ids=failed_ids)
            return build_runtime_service_response(payload=plan)
        except Exception as exc:
            return build_runtime_service_response(error=str(exc))

    def _handle_runtime_grasp_plan(self, request: Any, response: Any) -> Any:
        envelope = self._dispatch_runtime_grasp_plan(decode_runtime_service_payload(getattr(request, 'request_json', ''), field_name='grasp request_json'))
        response.ok = bool(envelope.ok)
        response.error = str(envelope.error)
        response.plan_json = encode_runtime_service_payload(envelope.payload)
        return response

    def _on_generate_grasps(self, msg: String) -> None:
        if self._ros_enabled and not self.runtime_active:
            return
        payload = self._parse_json(msg.data)
        if not payload:
            return
        self.plan(payload.get('target') or {}, payload.get('place') or {}, failed_ids=list(payload.get('failedIds') or []))

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
        GraspPlannerNode(enable_ros_io=False)
        return
    lifecycle_main(GraspPlannerNode, args=args)
