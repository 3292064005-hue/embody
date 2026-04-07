from __future__ import annotations

import json
import time

try:
    import rclpy
    from rclpy.action import ActionServer, CancelResponse, GoalResponse
    from arm_backend_common.lifecycle_support import ManagedLifecycleNode, lifecycle_main
    from std_msgs.msg import String
    from arm_common import ActionNames, ActionTypes, TopicNames
except Exception:  # pragma: no cover
    rclpy = None
    ActionServer = object
    CancelResponse = GoalResponse = object
    ManagedLifecycleNode = object

    def lifecycle_main(factory, args=None):
        del factory, args
        raise RuntimeError('rclpy unavailable')
    String = object

    class TopicNames:
        READINESS_UPDATE = '/arm/readiness/update'
        MOTION_PLANNER_SUMMARY = '/arm/motion_planner/summary'
        INTERNAL_PLAN_REQUEST = '/arm/internal/plan_request'
        INTERNAL_PLAN_RESULT = '/arm/internal/plan_result'
        INTERNAL_PLAN_TO_POSE = '/arm/internal/plan_to_pose'
        INTERNAL_PLAN_TO_JOINTS = '/arm/internal/plan_to_joints'

    class ActionNames:
        MANUAL_SERVO = '/arm/manual_servo'

    class _ActionTypes:
        ManualServo = object

    ActionTypes = _ActionTypes()

from arm_backend_common.data_models import CalibrationProfile, TargetSnapshot, TaskContext
from arm_common.runtime_contracts import build_planning_result
from .planner import MotionPlanner


class MotionPlannerNode(ManagedLifecycleNode):
    def __init__(self) -> None:
        super().__init__('motion_planner_node')
        self.declare_parameter('publish_period_sec', 1.0)
        self._planner = MotionPlanner()
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

    def _emit_summary(self, payload: dict) -> None:
        payload = {**payload, 'workspace': self._planner.workspace, 'updatedAt': round(time.time(), 3)}
        self._summary.publish(String(data=json.dumps(payload, ensure_ascii=False)))

    def _publish_status(self) -> None:
        if not self.runtime_active:
            return
        self._pub.publish(String(data=json.dumps({'check': 'motion_planner', 'ok': True, 'detail': 'planner_ready', 'staleAfterSec': 2.5}, ensure_ascii=False)))
        self._emit_summary({'status': 'ready', 'lastPlan': self._last_plan_summary, 'lastServo': self._last_servo_summary})

    def _on_plan_request(self, msg: String) -> None:
        """Handle orchestrator split-stack planning requests."""
        if not self.runtime_active:
            return
        payload = self._parse_json(msg.data)
        request_id = str(payload.get('requestId', ''))
        correlation_id = str(payload.get('correlationId', ''))
        task_run_id = str(payload.get('taskRunId', ''))
        task_id = str(payload.get('taskId', ''))
        try:
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
                task_id=str(context_payload.get('task_id', task_id)),
                task_type=str(context_payload.get('task_type', 'pick_place')),
                target_selector=str(context_payload.get('target_selector', target.target_type)),
                place_profile=str(context_payload.get('place_profile', 'default')),
                active_place_pose=dict(context_payload.get('active_place_pose') or {}),
            )
            plan = self._planner.build_pick_place_plan(context, target, calibration)
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
                task_id=str(context_payload.get('task_id', 'planner-preview')),
                task_type=str(context_payload.get('task_type', 'pick_place')),
                target_selector=str(context_payload.get('target_selector', target.target_type)),
                place_profile=str(context_payload.get('place_profile', 'default')),
                active_place_pose=dict(context_payload.get('active_place_pose') or {}),
            )
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
    def _parse_json(payload: str) -> dict:
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
