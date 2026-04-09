from __future__ import annotations

import json
import time
from typing import Any

try:
    import rclpy
    from rclpy.action import ActionServer, CancelResponse, GoalResponse
    from arm_backend_common import RosJsonRuntimeServiceClient
    from arm_backend_common.lifecycle_support import ManagedLifecycleNode, lifecycle_main
    from std_msgs.msg import String
    from arm_common import ActionNames, ActionTypes, ServiceNames, SrvTypes, TopicNames
except Exception:  # pragma: no cover
    rclpy = None
    ActionServer = object
    CancelResponse = GoalResponse = object
    ManagedLifecycleNode = object

    def lifecycle_main(factory, args=None):
        del factory, args
        raise RuntimeError('rclpy unavailable')
    String = object

    RosJsonRuntimeServiceClient = object

    class TopicNames:
        READINESS_UPDATE = '/arm/readiness/update'
        MOTION_PLANNER_SUMMARY = '/arm/motion_planner/summary'
        INTERNAL_PLAN_REQUEST = '/arm/internal/plan_request'
        INTERNAL_PLAN_RESULT = '/arm/internal/plan_result'
        INTERNAL_PLAN_TO_POSE = '/arm/internal/plan_to_pose'
        INTERNAL_PLAN_TO_JOINTS = '/arm/internal/plan_to_joints'

    class ServiceNames:
        RUNTIME_SCENE_SNAPSHOT = '/arm/internal/runtime_scene_snapshot'
        RUNTIME_GRASP_PLAN = '/arm/internal/runtime_grasp_plan'

    class _SrvTypes:
        RuntimeSceneSnapshot = object
        RuntimeGraspPlan = object

    SrvTypes = _SrvTypes()

    class ActionNames:
        MANUAL_SERVO = '/arm/manual_servo'

    class _ActionTypes:
        ManualServo = object

    ActionTypes = _ActionTypes()

from arm_backend_common.data_models import CalibrationProfile, TargetSnapshot, TaskContext
from arm_common.runtime_contracts import build_planning_result
from .backend_factory import effective_backend_config_path, resolve_planning_backend
from .moveit_client import MoveItClient
from .planner import MotionPlanner
from .providers import (
    GraspPlannerAdapter,
    GraspRuntimeServiceAdapter,
    SceneManagerAdapter,
    SceneRuntimeServiceAdapter,
)


class MotionPlannerNode(ManagedLifecycleNode):
    """Runtime motion-planner node with truthful planning-capability semantics."""

    def __init__(self) -> None:
        super().__init__('motion_planner_node')
        self.declare_parameter('publish_period_sec', 1.0)
        self.declare_parameter('planning_capability', 'contract_only')
        self.declare_parameter('planning_authoritative', False)
        self.declare_parameter('planning_backend_name', 'fallback_contract')
        self.declare_parameter('planning_backend_profile', '')
        self.declare_parameter('planning_backend_config_path', '')
        self.declare_parameter('scene_provider_mode', 'embedded_core')
        self.declare_parameter('grasp_provider_mode', 'embedded_core')
        self._planning_capability = str(self.get_parameter('planning_capability').value or 'contract_only')
        self._planning_authoritative = bool(self.get_parameter('planning_authoritative').value)
        self._planning_backend_name = str(self.get_parameter('planning_backend_name').value or 'fallback_contract')
        self._planning_backend_profile = str(self.get_parameter('planning_backend_profile').value or '')
        self._planning_backend_config_path = str(self.get_parameter('planning_backend_config_path').value or '')
        self._scene_provider_mode = str(self.get_parameter('scene_provider_mode').value or 'embedded_core')
        self._grasp_provider_mode = str(self.get_parameter('grasp_provider_mode').value or 'embedded_core')
        self._scene_runtime_client = None
        self._grasp_runtime_client = None
        scene_provider = self._build_scene_provider(self._scene_provider_mode)
        grasp_provider = self._build_grasp_provider(self._grasp_provider_mode)
        resolved_backend = resolve_planning_backend(
            capability_mode=self._planning_capability,
            backend_name=self._planning_backend_name,
            backend_profile=self._planning_backend_profile,
            backend_config_path=self._planning_backend_config_path,
        )
        self._planning_backend_declared = resolved_backend.declared
        self._planning_backend_profile = resolved_backend.profile_name or self._planning_backend_profile
        self._planning_backend_config_path = str(effective_backend_config_path(self._planning_backend_config_path))
        self._moveit_client = MoveItClient(
            planner_plugin=resolved_backend.planner_plugin or 'ompl',
            scene_source=resolved_backend.scene_source or 'planning_scene',
            planning_backend=resolved_backend.backend,
            capability_mode=self._planning_capability,
            authoritative=self._planning_authoritative,
            backend_name=self._planning_backend_name,
        )
        self._planner = MotionPlanner(
            moveit_client=self._moveit_client,
            scene_manager=scene_provider,
            grasp_planner=grasp_provider,
        )
        self._pub = self.create_managed_publisher(String, TopicNames.READINESS_UPDATE, 10)
        self._summary = self.create_managed_publisher(String, TopicNames.MOTION_PLANNER_SUMMARY, 10)
        self._plan_result_pub = self.create_managed_publisher(String, TopicNames.INTERNAL_PLAN_RESULT, 20)
        self._last_plan_summary = {'status': 'idle', 'workspace': self._planner.workspace}
        self._last_servo_summary = {'status': 'idle'}
        self.create_subscription(String, TopicNames.INTERNAL_PLAN_REQUEST, self._on_plan_request, 20)
        self.create_subscription(String, TopicNames.INTERNAL_PLAN_TO_POSE, self._on_plan_to_pose, 20)
        self.create_subscription(String, TopicNames.INTERNAL_PLAN_TO_JOINTS, self._on_plan_to_joints, 20)
        self._manual_servo_action_server = None
        self._create_action_servers()
        self.create_timer(float(self.get_parameter('publish_period_sec').value), self._publish_status)

    def _build_scene_provider(self, mode: str):
        normalized = str(mode or 'embedded_core').strip().lower() or 'embedded_core'
        if normalized == 'embedded_core':
            return SceneManagerAdapter()
        if normalized == 'runtime_service':
            client = RosJsonRuntimeServiceClient(
                node=self,
                service_name=ServiceNames.RUNTIME_SCENE_SNAPSHOT,
                srv_type=getattr(SrvTypes, 'RuntimeSceneSnapshot', object),
                response_json_field='snapshot_json',
                allow_local_fallback=False,
            ) if RosJsonRuntimeServiceClient is not object else None
            self._scene_runtime_client = client
            return SceneRuntimeServiceAdapter(client=client, authoritative=True)
        raise ValueError(f'unsupported scene_provider_mode: {mode!r}')

    def _build_grasp_provider(self, mode: str):
        normalized = str(mode or 'embedded_core').strip().lower() or 'embedded_core'
        if normalized == 'embedded_core':
            return GraspPlannerAdapter()
        if normalized == 'runtime_service':
            client = RosJsonRuntimeServiceClient(
                node=self,
                service_name=ServiceNames.RUNTIME_GRASP_PLAN,
                srv_type=getattr(SrvTypes, 'RuntimeGraspPlan', object),
                response_json_field='plan_json',
                allow_local_fallback=False,
            ) if RosJsonRuntimeServiceClient is not object else None
            self._grasp_runtime_client = client
            return GraspRuntimeServiceAdapter(client=client, authoritative=True)
        raise ValueError(f'unsupported grasp_provider_mode: {mode!r}')

    def _single_provider_boundary_status(self, provider_name: str) -> tuple[bool, str]:
        normalized = str(provider_name or '').strip().lower()
        if normalized == 'scene':
            if self._scene_provider_mode != 'runtime_service':
                return True, 'embedded_core'
            client = self._scene_runtime_client
            if client is None:
                return False, 'scene_runtime_service_client_unavailable'
            ready, detail = client.boundary_status()
            return ready, f'scene_{detail}' if not ready else detail
        if normalized == 'grasp':
            if self._grasp_provider_mode != 'runtime_service':
                return True, 'embedded_core'
            client = self._grasp_runtime_client
            if client is None:
                return False, 'grasp_runtime_service_client_unavailable'
            ready, detail = client.boundary_status()
            return ready, f'grasp_{detail}' if not ready else detail
        raise ValueError(f'unsupported provider boundary name: {provider_name!r}')

    def _provider_runtime_boundary_status(self) -> tuple[bool, str]:
        failures: list[str] = []
        scene_ready, scene_detail = self._single_provider_boundary_status('scene')
        if not scene_ready:
            failures.append(scene_detail)
        grasp_ready, grasp_detail = self._single_provider_boundary_status('grasp')
        if not grasp_ready:
            failures.append(grasp_detail)
        if failures:
            return False, failures[0]
        return True, 'runtime_service_boundaries_ready'

    def _create_action_servers(self) -> None:
        if ActionServer is object:
            return
        manual_servo_action = getattr(ActionTypes, 'ManualServo', object)
        if manual_servo_action is not object:
            self._manual_servo_action_server = ActionServer(
                self,
                manual_servo_action,
                ActionNames.MANUAL_SERVO,
                execute_callback=self._execute_manual_servo_action,
                goal_callback=lambda _goal: GoalResponse.ACCEPT,
                cancel_callback=lambda _goal: CancelResponse.ACCEPT,
            )

    def _planning_runtime_ready(self) -> bool:
        provider_ready, _provider_detail = self._provider_runtime_boundary_status()
        return (
            self._planning_capability in {'validated_sim', 'validated_live'}
            and self._planning_authoritative
            and self._moveit_client.planning_backend_ready()
            and provider_ready
        )

    def _planning_runtime_detail(self) -> str:
        if self._planning_capability == 'disabled':
            return 'planner_disabled'
        provider_ready, provider_detail = self._provider_runtime_boundary_status()
        if self._planning_capability == 'validated_live' and not self._moveit_client.planning_backend_ready():
            return 'planner_backend_unavailable'
        if not provider_ready:
            return provider_detail
        if self._planning_runtime_ready():
            return 'planner_ready'
        if self._planning_capability == 'contract_only':
            return 'planner_contract_only'
        return 'planner_not_authoritative'

    def _planner_status_payload(self) -> dict[str, Any]:
        return {
            'planningCapability': self._planning_capability,
            'planningAuthoritative': self._planning_authoritative,
            'planningBackend': self._planning_backend_name,
            'planningBackendProfile': self._planning_backend_profile,
            'planningBackendConfigPath': self._planning_backend_config_path,
            'planningBackendDeclared': self._planning_backend_declared,
            'planningBackendReady': self._moveit_client.planning_backend_ready(),
            'sceneProviderMode': self._scene_provider_mode,
            'graspProviderMode': self._grasp_provider_mode,
            'sceneRuntimeBoundary': self._single_provider_boundary_status('scene')[1],
            'graspRuntimeBoundary': self._single_provider_boundary_status('grasp')[1],
            'workspace': self._planner.workspace,
        }

    def _emit_summary(self, payload: dict[str, Any]) -> None:
        payload = {
            **self._planner_status_payload(),
            **payload,
            'workspace': self._planner.workspace,
            'updatedAt': round(time.time(), 3),
        }
        self._summary.publish(String(data=json.dumps(payload, ensure_ascii=False)))

    def _publish_status(self) -> None:
        if not self.runtime_active:
            return
        self._pub.publish(
            String(
                data=json.dumps(
                    {
                        'check': 'motion_planner',
                        'ok': self._planning_runtime_ready(),
                        'detail': self._planning_runtime_detail(),
                        'staleAfterSec': 2.5,
                    },
                    ensure_ascii=False,
                )
            )
        )
        self._emit_summary({'status': 'ready' if self._planning_runtime_ready() else 'limited', 'lastPlan': self._last_plan_summary, 'lastServo': self._last_servo_summary})

    def _reject_non_authoritative_request(self, *, request_id: str, task_id: str, correlation_id: str, task_run_id: str) -> None:
        message = f'planning capability not authoritative: {self._planning_runtime_detail()}'
        self._last_plan_summary = {'status': 'rejected', 'requestKind': 'runtime_contract', 'message': message}
        self._emit_summary(self._last_plan_summary)
        result = build_planning_result(
            request_id=request_id,
            task_id=task_id,
            accepted=False,
            message=message,
            plan=[],
            correlation_id=correlation_id,
            task_run_id=task_run_id,
        )
        self._plan_result_pub.publish(String(data=json.dumps(result, ensure_ascii=False)))

    def _build_context(self, *, payload: dict[str, Any], default_task_id: str) -> tuple[TargetSnapshot, CalibrationProfile, TaskContext]:
        target_payload = payload.get('target') or {}
        calibration_payload = payload.get('calibration') or {}
        context_payload = payload.get('context') or {}
        target = TargetSnapshot(
            target_id=str(target_payload.get('target_id', 'planner_target')),
            target_type=str(target_payload.get('target_type', 'unknown')),
            semantic_label=str(target_payload.get('semantic_label', target_payload.get('target_type', 'unknown'))),
            table_x=float(target_payload.get('table_x', 0.0)),
            table_y=float(target_payload.get('table_y', 0.0)),
            yaw=float(target_payload.get('yaw', 0.0)),
            confidence=float(target_payload.get('confidence', 1.0)),
        )
        calibration = CalibrationProfile(**{key: value for key, value in calibration_payload.items() if key in CalibrationProfile.__dataclass_fields__})
        context = TaskContext(
            task_id=str(context_payload.get('task_id', default_task_id)),
            task_type=str(context_payload.get('task_type', 'pick_place')),
            target_selector=str(context_payload.get('target_selector', target.target_type)),
            place_profile=str(context_payload.get('place_profile', 'default')),
            active_place_pose=dict(context_payload.get('active_place_pose') or {}),
        )
        return target, calibration, context

    def _on_plan_request(self, msg: String) -> None:
        """Handle orchestrator split-stack planning requests."""
        if not self.runtime_active:
            return
        payload = self._parse_json(msg.data)
        request_id = str(payload.get('requestId', ''))
        correlation_id = str(payload.get('correlationId', ''))
        task_run_id = str(payload.get('taskRunId', ''))
        task_id = str(payload.get('taskId', ''))
        if not self._planning_runtime_ready():
            self._reject_non_authoritative_request(request_id=request_id, task_id=task_id, correlation_id=correlation_id, task_run_id=task_run_id)
            return
        try:
            target, calibration, context = self._build_context(payload=payload, default_task_id=task_id)
            plan = self._planner.build_pick_place_plan(context, target, calibration)
            if self._planning_capability == 'validated_live' and self._planning_authoritative:
                plan = self._planner.attach_runtime_execution_targets(plan)
            summary = self._planner.summarize_plan(plan)
            self._last_plan_summary = {'status': 'planned', 'requestKind': 'runtime_contract', **summary}
            self._emit_summary(self._last_plan_summary)
            result = build_planning_result(
                request_id=request_id,
                task_id=context.task_id,
                accepted=True,
                message='plan ready',
                plan=plan,
                correlation_id=correlation_id,
                task_run_id=task_run_id,
            )
        except Exception as exc:
            self._last_plan_summary = {'status': 'rejected', 'requestKind': 'runtime_contract', 'message': str(exc)}
            self._emit_summary(self._last_plan_summary)
            result = build_planning_result(
                request_id=request_id,
                task_id=task_id,
                accepted=False,
                message=str(exc),
                plan=[],
                correlation_id=correlation_id,
                task_run_id=task_run_id,
            )
        self._plan_result_pub.publish(String(data=json.dumps(result, ensure_ascii=False)))

    def _on_plan_to_pose(self, msg: String) -> None:
        if not self.runtime_active:
            return
        payload = self._parse_json(msg.data)
        try:
            target, calibration, context = self._build_context(payload=payload, default_task_id='planner-preview')
            plan = self._planner.build_pick_place_plan(context, target, calibration)
            summary = self._planner.summarize_plan(plan)
            self._last_plan_summary = {'status': 'planned', 'requestKind': 'pose', **summary}
            self._emit_summary(self._last_plan_summary)
        except Exception as exc:
            self._last_plan_summary = {'status': 'rejected', 'requestKind': 'pose', 'message': str(exc)}
            self._emit_summary(self._last_plan_summary)

    def _on_plan_to_joints(self, msg: String) -> None:
        if not self.runtime_active:
            return
        payload = self._parse_json(msg.data)
        joints = payload.get('joints') or []
        accepted = isinstance(joints, list) and len(joints) > 0 and all(isinstance(value, (int, float)) for value in joints)
        if accepted:
            self._last_plan_summary = {'status': 'planned', 'requestKind': 'joints', 'jointCount': len(joints), 'jointGoal': [float(v) for v in joints]}
        else:
            self._last_plan_summary = {'status': 'rejected', 'requestKind': 'joints', 'message': 'joint request must provide a non-empty numeric joint list'}
        self._emit_summary(self._last_plan_summary)

    async def _execute_manual_servo_action(self, goal_handle):
        request = goal_handle.request
        try:
            command = self._planner.build_servo_command(str(getattr(request, 'axis', '')), float(getattr(request, 'delta', 0.0)))
            self._last_servo_summary = {'status': 'accepted', 'axis': command.axis, 'delta': command.delta, 'frame': command.frame}
            feedback = ActionTypes.ManualServo.Feedback()
            feedback.stage = 'command_built'
            feedback.progress = 1.0
            goal_handle.publish_feedback(feedback)
            result = ActionTypes.ManualServo.Result()
            result.accepted = True
            result.message = f'servo command prepared for {command.axis}'
            goal_handle.succeed()
            self._emit_summary({'status': 'servo_ready', 'lastServo': self._last_servo_summary})
            return result
        except Exception as exc:
            self._last_servo_summary = {'status': 'rejected', 'message': str(exc)}
            result = ActionTypes.ManualServo.Result()
            result.accepted = False
            result.message = str(exc)
            goal_handle.abort()
            self._emit_summary({'status': 'servo_rejected', 'lastServo': self._last_servo_summary})
            return result

    @staticmethod
    def _parse_json(payload: str) -> dict[str, Any]:
        if not payload:
            return {}
        try:
            parsed = json.loads(payload)
        except Exception:
            return {}
        return parsed if isinstance(parsed, dict) else {}


def main(args=None) -> None:  # pragma: no cover
    if rclpy is None:
        raise RuntimeError('rclpy unavailable')
    lifecycle_main(MotionPlannerNode, args=args)
