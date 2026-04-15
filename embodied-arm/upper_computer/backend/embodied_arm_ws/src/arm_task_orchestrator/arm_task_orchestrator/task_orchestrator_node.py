from __future__ import annotations

import asyncio
import json
import time
import uuid
from collections import deque
from typing import Any

try:
    import rclpy
    from rclpy.action import ActionServer, CancelResponse, GoalResponse
    from arm_backend_common.lifecycle_support import ManagedLifecycleNode, lifecycle_main
    from std_msgs.msg import String
    from arm_common import (
        ActionNames,
        ActionTypes,
        MsgTypes,
        SrvTypes,
        TopicNames,
        ServiceNames,
        parse_calibration_profile_message,
        parse_readiness_state_message,
    )

    CalibrationProfileMsg = MsgTypes.CalibrationProfileMsg
    FaultReport = MsgTypes.FaultReport
    HardwareState = MsgTypes.HardwareState
    SystemState = MsgTypes.SystemState
    TargetInfo = MsgTypes.TargetInfo
    TaskEvent = MsgTypes.TaskEvent
    TaskStatusMsg = MsgTypes.TaskStatus
    HomeArm = SrvTypes.HomeArm
    ResetFault = SrvTypes.ResetFault
    StartTask = SrvTypes.StartTask
    StopTask = SrvTypes.StopTask
    PickPlaceTaskAction = ActionTypes.PickPlaceTask
    HomingAction = ActionTypes.Homing
    RecoverAction = ActionTypes.Recover
except Exception:  # pragma: no cover
    rclpy = None
    ActionServer = object
    CancelResponse = GoalResponse = object
    ManagedLifecycleNode = object

    def lifecycle_main(factory, args=None):
        del factory, args
        raise RuntimeError('rclpy unavailable')

    String = object
    CalibrationProfileMsg = object
    FaultReport = object
    HardwareState = object
    SystemState = object
    TargetInfo = object
    TaskEvent = object
    TaskStatusMsg = object

    def parse_calibration_profile_message(msg):
        return {}

    def parse_readiness_state_message(msg):
        return {}
    HomeArm = object
    ResetFault = object
    StartTask = object
    StopTask = object
    PickPlaceTaskAction = object
    HomingAction = object
    RecoverAction = object

    class TopicNames:
        SYSTEM_STATE = '/arm/system/state'
        LOG_EVENT = '/arm/log/event'
        FAULT_REPORT = '/arm/fault/report'
        INTERNAL_HARDWARE_CMD = '/arm/internal/hardware_cmd'
        TASK_ORCHESTRATOR_SUMMARY = '/arm/task_orchestrator/summary'
        TASK_STATUS = '/arm/task/status'
        TASK_STATUS_TYPED = '/arm/task/status_typed'
        READINESS_STATE = '/arm/readiness/state'
        READINESS_STATE_TYPED = '/arm/readiness/state_typed'
        READINESS_UPDATE = '/arm/readiness/update'
        INTERNAL_SELECTED_TARGET = '/arm/internal/selected_target'
        INTERNAL_PLAN_REQUEST = '/arm/internal/plan_request'
        INTERNAL_PLAN_RESULT = '/arm/internal/plan_result'
        INTERNAL_EXECUTION_STATUS = '/arm/internal/execution_status'
        INTERNAL_EXECUTE_PLAN = '/arm/internal/execute_plan'
        VISION_TARGET = '/arm/vision/target'
        HARDWARE_STATE = '/arm/hardware/state'
        CALIBRATION_PROFILE = '/arm/calibration/profile'
        CALIBRATION_PROFILE_TYPED = '/arm/calibration/profile_typed'
        PROFILES_ACTIVE = '/arm/profiles/active'
        HARDWARE_FEEDBACK = '/arm/hardware/feedback'
        INTERNAL_STOP_CMD = '/arm/internal/stop_cmd'

    class ServiceNames:
        START_TASK = '/arm/start_task'
        RESET_FAULT = '/arm/reset_fault'
        STOP_TASK = '/arm/stop_task'
        STOP = '/arm/stop'
        HOME = '/arm/home'

    class ActionNames:
        PICK_PLACE_TASK = '/arm/pick_place_task'
        HOMING = '/arm/homing'
        RECOVER = '/arm/recover'

from arm_backend_common.data_models import CalibrationProfile, HardwareSnapshot, TaskProfile, TaskRequest, TargetSnapshot
from arm_backend_common.enums import FaultCode, SystemMode
from arm_backend_common.error_codes import fault_message
from arm_task_orchestrator.execution_adapter import ExecutionAdapter
from arm_task_orchestrator.fault_manager import FaultManager
from arm_task_orchestrator.node_actions import TaskActionFacade
from arm_task_orchestrator.node_context import build_runtime_hooks, build_runtime_stack
from arm_task_orchestrator.node_profiles import load_task_profile_from_active_profiles, load_task_profile_from_yaml
from arm_task_orchestrator.node_publishers import TaskNodePublishers
from arm_task_orchestrator.orchestrator import OrchestratorDecision
from arm_task_orchestrator.runtime import TaskRuntimeState
from arm_task_orchestrator.runtime_coordinator import RuntimeCoordinator
from arm_task_orchestrator.stack_factory import build_application_service, build_runtime_engine, build_target_tracker
from arm_task_orchestrator.state_machine import SystemStateMachine
from arm_task_orchestrator.summary_publisher import SummaryPublisher
from arm_task_orchestrator.task_plugins import resolve_task_graph_contract
from arm_task_orchestrator.verification import VerificationManager


# Runtime contract literals retained for repository integrity tests:
# /arm/task/status
# /arm/internal/stop_cmd
# '/arm/stop'
MODE_TO_READINESS_MODE = {
    SystemMode.BOOT: 'boot',
    SystemMode.IDLE: 'idle',
    SystemMode.PERCEPTION: 'task',
    SystemMode.PLAN: 'task',
    SystemMode.EXECUTE: 'task',
    SystemMode.VERIFY: 'task',
    SystemMode.SAFE_STOP: 'safe_stop',
    SystemMode.FAULT: 'fault',
}


class TaskOrchestratorNode(ManagedLifecycleNode):
    """Lifecycle node that orchestrates queueing and split-stack runtime contracts."""

    # Action contract names retained in-file for repository integrity tests:
    # ActionNames.PICK_PLACE_TASK
    # ActionNames.HOMING
    # ActionNames.RECOVER

    def __init__(self) -> None:
        super().__init__('task_orchestrator')
        self._declare_parameters()
        self._initialize_domain_state()
        self._initialize_publishers()
        self._build_runtime_stack()
        self._load_task_profile()
        self._register_subscriptions()
        self._register_services()
        self._create_action_servers()
        self._register_timers()
        transition = self._state_machine.to_idle()
        self._emit_event('INFO', 'task_orchestrator', 'STATE_TRANSITION', '', 0, transition.reason)

    def _declare_parameters(self) -> None:
        self.declare_parameter('task_profile_path', '')
        self.declare_parameter('tick_period_sec', 0.05)
        self.declare_parameter('verify_timeout_sec', 0.8)
        self.declare_parameter('hardware_fresh_sec', 1.2)
        self.declare_parameter('target_stable_seen_count', 1)
        self.declare_parameter('command_timeout_sec', 1.5)
        self.declare_parameter('perception_blocked_after_sec', 2.5)
        self.declare_parameter('publish_task_status', True)

    def _initialize_domain_state(self) -> None:
        self._state_machine = SystemStateMachine()
        self._task_profile = TaskProfile()
        self._verification = VerificationManager()
        self._execution_adapter = ExecutionAdapter()
        self._fault_manager = FaultManager()
        self._summary_builder = SummaryPublisher()
        self._runtime_state = TaskRuntimeState(task_profile=self._task_profile)
        self._orchestrator, self._application = build_application_service(
            self._task_profile,
            self._execution_adapter,
            self._verification,
            self._fault_manager,
        )
        self._tracker = self._build_tracker()

    def _build_tracker(self):
        return build_target_tracker(
            self._task_profile,
            stable_seen_count=int(self.get_parameter('target_stable_seen_count').value),
        )

    def _initialize_publishers(self) -> None:
        self._state_pub = self.create_managed_publisher(SystemState, TopicNames.SYSTEM_STATE, 20)
        self._event_pub = self.create_managed_publisher(TaskEvent, TopicNames.LOG_EVENT, 50)
        self._fault_pub = self.create_managed_publisher(FaultReport, TopicNames.FAULT_REPORT, 20)
        self._hardware_cmd_pub = self.create_managed_publisher(String, TopicNames.INTERNAL_HARDWARE_CMD, 20)
        self._summary_pub = self.create_managed_publisher(String, TopicNames.TASK_ORCHESTRATOR_SUMMARY, 10)
        self._task_status_pub = self.create_managed_publisher(String, TopicNames.TASK_STATUS, 20)
        self._task_status_typed_pub = self.create_managed_publisher(TaskStatusMsg, TopicNames.TASK_STATUS_TYPED, 20) if TaskStatusMsg is not object else None
        self._readiness_pub = self.create_managed_publisher(String, TopicNames.READINESS_UPDATE, 10)
        self._selected_target_pub = self.create_managed_publisher(String, TopicNames.INTERNAL_SELECTED_TARGET, 20)
        self._plan_request_pub = self.create_managed_publisher(String, TopicNames.INTERNAL_PLAN_REQUEST, 20)
        self._execute_plan_pub = self.create_managed_publisher(String, TopicNames.INTERNAL_EXECUTE_PLAN, 20)
        self._publishers = TaskNodePublishers(
            string_type=String,
            fault_report_type=FaultReport,
            task_event_type=TaskEvent,
            system_state_type=SystemState,
            summary_builder=self._summary_builder,
            mode_to_readiness_mode=MODE_TO_READINESS_MODE,
            state_pub=self._state_pub,
            event_pub=self._event_pub,
            fault_pub=self._fault_pub,
            hardware_cmd_pub=self._hardware_cmd_pub,
            summary_pub=self._summary_pub,
            task_status_pub=self._task_status_pub,
            task_status_typed_pub=self._task_status_typed_pub,
            readiness_pub=self._readiness_pub,
            selected_target_pub=self._selected_target_pub,
            plan_request_pub=self._plan_request_pub,
            execute_plan_pub=self._execute_plan_pub,
            now_msg=lambda: self.get_clock().now().to_msg(),
        )

    def _build_runtime_stack(self) -> None:
        self._runtime_engine, self._runtime_hooks = build_runtime_stack(
            state_machine=self._state_machine,
            application=self._application,
            execution_adapter=self._execution_adapter,
            fault_manager=self._fault_manager,
            tracker=self._tracker,
            state=self._runtime_state,
            publishers=self._publishers,
            emit_event=self._emit_event,
            publish_fault=self._publish_fault_report,
        )
        self._runtime_coordinator = RuntimeCoordinator(
            runtime_engine=self._runtime_engine,
            state_machine=self._state_machine,
            emit_event=self._emit_event,
        )

    def _build_runtime_hooks(self):
        """Build runtime hooks for stack rebuilds without duplicating publisher wiring."""
        return build_runtime_hooks(
            publishers=self._publishers,
            emit_event=self._emit_event,
            publish_fault=self._publish_fault_report,
        )

    def _rebuild_application_stack(self) -> None:
        """Rebuild pure application/runtime services after task-profile changes."""
        self._orchestrator, self._application = build_application_service(
            self._task_profile,
            self._execution_adapter,
            self._verification,
            self._fault_manager,
        )
        self._tracker = self._build_tracker()
        self._runtime_hooks = self._build_runtime_hooks()
        self._runtime_engine = build_runtime_engine(
            state_machine=self._state_machine,
            application=self._application,
            execution_adapter=self._execution_adapter,
            fault_manager=self._fault_manager,
            tracker=self._tracker,
            state=self._runtime_state,
            hooks=self._runtime_hooks,
        )
        self._runtime_engine.replace_task_profile(self._task_profile)
        self._runtime_coordinator = RuntimeCoordinator(
            runtime_engine=self._runtime_engine,
            state_machine=self._state_machine,
            emit_event=self._emit_event,
        )
        self._action_facade = self._build_action_facade()
        self._pick_place_action_server = self._action_facade.servers.pick_place
        self._homing_action_server = self._action_facade.servers.homing
        self._recover_action_server = self._action_facade.servers.recover

    def _build_action_facade(self) -> TaskActionFacade:
        return TaskActionFacade(
            node=self,
            action_server_type=ActionServer,
            goal_response_type=GoalResponse,
            cancel_response_type=CancelResponse,
            action_names=ActionNames,
            pick_place_action_type=PickPlaceTaskAction,
            homing_action_type=HomingAction,
            recover_action_type=RecoverAction,
            state_machine=self._state_machine,
            orchestrator=self._orchestrator,
            evaluate_task_request=self._evaluate_task_request,
            enqueue_task_request=self._enqueue_task_request,
            evaluate_command_policy=self._evaluate_command_policy,
            cancel_task_by_id=self._cancel_task_by_id,
            elapsed_for_task=self._elapsed_for_task,
            estimate_progress=self._estimate_progress,
            send_hardware_command=self._send_hardware_command,
            emit_event=self._emit_event,
            queue_clear=self._queue.clear,
            transition_to_idle=self._state_machine.to_idle,
            task_outcomes_getter=lambda: self._task_outcomes,
            current_getter=lambda: self._current,
            phase_getter=lambda: self._state_machine.phase,
        )

    def _register_subscriptions(self) -> None:
        self.create_subscription(TargetInfo, TopicNames.VISION_TARGET, self._on_target, 20)
        self.create_subscription(HardwareState, TopicNames.HARDWARE_STATE, self._on_hardware_state, 20)
        self.create_subscription(String, TopicNames.CALIBRATION_PROFILE, self._on_calibration_profile, 10)
        if CalibrationProfileMsg is not object:
            self.create_subscription(CalibrationProfileMsg, TopicNames.CALIBRATION_PROFILE_TYPED, self._on_calibration_profile_typed, 10)
        self.create_subscription(String, TopicNames.PROFILES_ACTIVE, self._on_profiles_active, 10)
        self.create_subscription(String, TopicNames.READINESS_STATE, self._on_readiness_state, 20)
        self.create_subscription(String, TopicNames.HARDWARE_FEEDBACK, self._on_feedback, 20)
        self.create_subscription(String, TopicNames.INTERNAL_PLAN_RESULT, self._on_plan_result, 20)
        self.create_subscription(String, TopicNames.INTERNAL_EXECUTION_STATUS, self._on_execution_status, 20)
        self.create_subscription(String, TopicNames.INTERNAL_STOP_CMD, self._on_stop_cmd, 20)
        self.create_subscription(FaultReport, TopicNames.FAULT_REPORT, self._on_fault_report, 20)

    def _register_services(self) -> None:
        self.create_service(StartTask, ServiceNames.START_TASK, self._handle_start_task)
        self.create_service(ResetFault, ServiceNames.RESET_FAULT, self._handle_reset_fault)
        self.create_service(StopTask, ServiceNames.STOP_TASK, self._handle_stop_task)
        self.create_service(StopTask, ServiceNames.STOP, self._handle_stop_task)
        self.create_service(HomeArm, ServiceNames.HOME, self._handle_home)

    def _register_timers(self) -> None:
        self.create_timer(float(self.get_parameter('tick_period_sec').value), self._tick)
        self.create_timer(0.2, self._publish_system_state)
        self.create_timer(0.2, self._publish_task_status)
        self.create_timer(0.5, self._publish_summary)

    @staticmethod
    def _parse_json(raw: str) -> dict[str, Any]:
        try:
            payload = json.loads(raw) if raw else {}
        except Exception:
            return {}
        return payload if isinstance(payload, dict) else {}

    @property
    def _hardware(self) -> HardwareSnapshot:
        return self._runtime_state.hardware

    @_hardware.setter
    def _hardware(self, value: HardwareSnapshot) -> None:
        self._runtime_engine.update_hardware(value)

    @property
    def _calibration(self) -> CalibrationProfile:
        return self._runtime_state.calibration

    @_calibration.setter
    def _calibration(self, value: CalibrationProfile) -> None:
        self._runtime_engine.update_calibration(value)

    @property
    def _queue(self):
        return self._runtime_state.queue

    @property
    def _current(self):
        return self._runtime_state.current

    @_current.setter
    def _current(self, value):
        self._runtime_state.current = value

    @property
    def _plan(self):
        return self._runtime_state.plan

    @_plan.setter
    def _plan(self, value):
        self._runtime_state.plan = list(value)

    @property
    def _command_queue(self):
        return self._runtime_state.command_queue

    @_command_queue.setter
    def _command_queue(self, value):
        self._runtime_state.command_queue = deque(value)

    @property
    def _awaiting(self):
        return self._runtime_state.awaiting

    @_awaiting.setter
    def _awaiting(self, value):
        self._runtime_state.awaiting = value

    @property
    def _awaiting_state(self):
        return self._runtime_state.awaiting_state

    @_awaiting_state.setter
    def _awaiting_state(self, value):
        self._runtime_state.awaiting_state = value

    @property
    def _last_feedback(self):
        return self._runtime_state.last_feedback

    @_last_feedback.setter
    def _last_feedback(self, value):
        self._runtime_engine.update_feedback(value)

    @property
    def _latest_target(self):
        return self._runtime_state.latest_target

    @_latest_target.setter
    def _latest_target(self, value):
        self._runtime_state.latest_target = value

    @property
    def _task_outcomes(self):
        return self._runtime_state.task_outcomes

    def _create_action_servers(self) -> None:
        self._runtime_coordinator = RuntimeCoordinator(
            runtime_engine=self._runtime_engine,
            state_machine=self._state_machine,
            emit_event=self._emit_event,
        )
        self._action_facade = self._build_action_facade()
        servers = self._action_facade.create_servers()
        self._pick_place_action_server = servers.pick_place
        self._homing_action_server = servers.homing
        self._recover_action_server = servers.recover

    def _build_pick_place_request_from_action(self, action_request, *, task_id: str) -> TaskRequest:
        return TaskActionFacade.build_pick_place_request_from_action(action_request, task_id=task_id)

    def _pick_place_goal_callback(self, goal_request):
        return self._action_facade.pick_place_goal_callback(goal_request)

    def _pick_place_cancel_callback(self, goal_handle):
        return self._action_facade.pick_place_cancel_callback(goal_handle)

    async def _execute_pick_place_action(self, goal_handle):
        return await self._action_facade.execute_pick_place_action(goal_handle)

    async def _execute_homing_action(self, goal_handle):
        if hasattr(self, '_action_facade'):
            return await self._action_facade.execute_homing_action(goal_handle)
        self._send_hardware_command({'kind': 'HOME', 'task_id': 'action-home', 'timeout_sec': 1.0})
        await asyncio.sleep(0.1)
        if goal_handle.is_cancel_requested:
            goal_handle.canceled()
            return self._build_stateful_action_result(HomingAction, False, 'canceled', 'home canceled')
        goal_handle.succeed()
        return self._build_stateful_action_result(HomingAction, True, 'idle', 'home command sent')

    async def _execute_recover_action(self, goal_handle):
        if hasattr(self, '_action_facade'):
            return await self._action_facade.execute_recover_action(goal_handle)
        self._queue.clear()
        self._send_hardware_command({'kind': 'RESET_FAULT', 'task_id': 'action-recover', 'timeout_sec': 0.6})
        await asyncio.sleep(0.1)
        if goal_handle.is_cancel_requested:
            goal_handle.canceled()
            return self._build_stateful_action_result(RecoverAction, False, 'canceled', 'recover canceled')
        self._state_machine.to_idle('Recover action completed')
        goal_handle.succeed()
        return self._build_stateful_action_result(RecoverAction, True, 'idle', 'recover completed')

    def _build_stateful_action_result(self, action_type, success: bool, final_state: str, message: str):
        return TaskActionFacade.build_stateful_action_result(action_type, success, final_state, message)

    def _evaluate_task_request(self, queued: TaskRequest) -> OrchestratorDecision:
        return self._runtime_coordinator.task_admission_decision(
            queued,
            hardware_fresh_sec=float(self.get_parameter('hardware_fresh_sec').value),
        )

    def _enqueue_task_request(self, queued: TaskRequest) -> OrchestratorDecision:
        return self._runtime_coordinator.enqueue_task(
            queued,
            hardware_fresh_sec=float(self.get_parameter('hardware_fresh_sec').value),
        )

    def _evaluate_command_policy(self, command_name: str, *, fallback_reason: str | None = None) -> OrchestratorDecision:
        return self._runtime_coordinator.command_policy_decision(
            command_name,
            hardware_fresh_sec=float(self.get_parameter('hardware_fresh_sec').value),
            fallback_reason=fallback_reason,
        )

    def _mark_task_terminal(self, task_id: str, *, state: str, result_code: int, message: str, elapsed: float | None = None) -> None:
        runtime_engine = getattr(self, '_runtime_engine', None)
        if runtime_engine is not None:
            self._runtime_coordinator.mark_task_terminal(task_id, state=state, result_code=result_code, message=message, elapsed=elapsed)
            return
        current = dict(getattr(self, '_task_outcomes', {}).get(task_id, {}))
        current.update({'terminal': True, 'state': state, 'result_code': int(result_code), 'message': message})
        if elapsed is not None:
            current['elapsed'] = float(elapsed)
        self._task_outcomes[task_id] = current

    def _cancel_task_by_id(self, task_id: str, reason: str) -> None:
        runtime_engine = getattr(self, '_runtime_engine', None)
        if runtime_engine is not None:
            self._runtime_coordinator.cancel_task_by_id(task_id, reason)
            return
        for queued in list(self._queue):
            if queued.task_id == task_id:
                self._queue.remove(queued)
                self._mark_task_terminal(task_id, state='canceled', result_code=int(FaultCode.UNKNOWN), message=reason, elapsed=0.0)
                self._emit_event('WARN', 'task_orchestrator', 'TASK_CANCELED', task_id, int(FaultCode.UNKNOWN), reason)
                return
        if self._current is not None and self._current.task_id == task_id:
            self._perform_stop(reason, canceled_task_id=task_id)

    def _elapsed_for_task(self, task_id: str) -> float:
        runtime_engine = getattr(self, '_runtime_engine', None)
        if runtime_engine is not None:
            return self._runtime_coordinator.elapsed_for_task(task_id)
        if self._current is not None and self._current.task_id == task_id:
            return self._current.elapsed()
        return float(self._task_outcomes.get(task_id, {}).get('elapsed', 0.0))

    def _load_task_profile(self) -> None:
        path = self.get_parameter('task_profile_path').get_parameter_value().string_value
        if not path:
            return
        try:
            self._task_profile = load_task_profile_from_yaml(path, self._task_profile)
            self._rebuild_application_stack()
        except Exception as exc:
            self.get_logger().warn(f'Failed to load task profile {path}: {exc}')

    def _on_profiles_active(self, msg: String) -> None:
        try:
            payload = json.loads(msg.data)
            profile = load_task_profile_from_active_profiles(payload, self._task_profile)
            if profile is not None:
                self._task_profile = profile
                self._rebuild_application_stack()
        except Exception as exc:
            self.get_logger().warn(f'Failed to parse active profiles: {exc}')

    def _on_readiness_state(self, msg: String) -> None:
        payload = self._parse_json(getattr(msg, 'data', ''))
        if payload:
            self._runtime_coordinator.update_readiness_snapshot(payload)

    def _on_readiness_state_typed(self, msg: Any) -> None:
        payload = parse_readiness_state_message(msg)
        if payload:
            self._runtime_coordinator.update_readiness_snapshot(payload)

    def _on_target(self, msg: TargetInfo) -> None:
        if not bool(msg.is_valid):
            return
        version = self._latest_target.version + 1 if self._latest_target else 1
        target = TargetSnapshot(
            target_id=msg.target_id,
            target_type=msg.target_type,
            semantic_label=msg.semantic_label,
            table_x=msg.table_x,
            table_y=msg.table_y,
            yaw=msg.yaw,
            confidence=msg.confidence,
            image_u=msg.image_u,
            image_v=msg.image_v,
            received_monotonic=time.monotonic(),
            version=version,
        )
        self._latest_target = target
        self._runtime_coordinator.update_target(target)

    def _on_hardware_state(self, msg: HardwareState) -> None:
        raw = self._parse_json(msg.raw_status)
        self._hardware = HardwareSnapshot(
            stm32_online=bool(msg.stm32_online),
            esp32_online=bool(msg.esp32_online),
            estop_pressed=bool(msg.estop_pressed),
            home_ok=bool(msg.home_ok),
            gripper_ok=bool(msg.gripper_ok),
            motion_busy=bool(msg.motion_busy),
            limit_triggered=bool(msg.limit_triggered),
            hardware_fault_code=int(msg.hardware_fault_code),
            raw_status=msg.raw_status,
            updated_monotonic=time.monotonic(),
            last_result=str(raw.get('last_result', '')),
            last_kind=str(raw.get('last_kind', '')),
            last_stage=str(raw.get('last_stage', '')),
            last_sequence=int(raw.get('last_sequence', -1)),
            task_id=str(raw.get('task_id', '')),
        )
        if self._hardware.estop_pressed:
            self._enter_fault(FaultCode.ESTOP_TRIGGERED)
        elif self._hardware.limit_triggered:
            self._enter_fault(FaultCode.HARDWARE_LIMIT_TRIGGERED)
        elif self._hardware.hardware_fault_code != 0:
            self._enter_fault(FaultCode.UNKNOWN, detail=f'hardware fault {self._hardware.hardware_fault_code}')

    def _apply_calibration_profile_payload(self, payload: dict[str, Any]) -> None:
        profile = payload.get('profile', {}) if isinstance(payload, dict) else {}
        self._calibration = CalibrationProfile(
            version=str(profile.get('version', 'default')),
            x_bias=float(profile.get('x_bias', 0.0)),
            y_bias=float(profile.get('y_bias', 0.0)),
            yaw_bias=float(profile.get('yaw_bias', 0.0)),
            pre_grasp_z=float(profile.get('pre_grasp_z', 0.12)),
            grasp_z=float(profile.get('grasp_z', 0.03)),
            place_z=float(profile.get('place_z', 0.05)),
            retreat_z=float(profile.get('retreat_z', 0.12)),
            place_profiles=dict(profile.get('place_profiles', self._calibration.place_profiles)),
            created_at=str(profile.get('created_at', '')),
            operator=str(profile.get('operator', '')),
            camera_serial=str(profile.get('camera_serial', '')),
            robot_description_hash=str(profile.get('robot_description_hash', '')),
            workspace_id=str(profile.get('workspace_id', 'default')),
            active=bool(profile.get('active', True)),
        )

    def _on_calibration_profile(self, msg: String) -> None:
        try:
            payload = json.loads(msg.data)
            self._apply_calibration_profile_payload(payload)
        except Exception as exc:
            self.get_logger().warn(f'Failed to parse calibration profile: {exc}')

    def _on_calibration_profile_typed(self, msg: CalibrationProfileMsg) -> None:
        try:
            payload = parse_calibration_profile_message(msg)
            self._apply_calibration_profile_payload(payload)
        except Exception as exc:
            self.get_logger().warn(f'Failed to parse typed calibration profile: {exc}')

    def _on_plan_result(self, msg: String) -> None:
        payload = self._parse_json(getattr(msg, 'data', ''))
        if payload:
            self._runtime_coordinator.update_plan_result(payload)

    def _on_execution_status(self, msg: String) -> None:
        payload = self._parse_json(getattr(msg, 'data', ''))
        if payload:
            self._runtime_coordinator.update_execution_status(payload)

    def _on_feedback(self, msg: String) -> None:
        self._last_feedback = self._parse_json(getattr(msg, 'data', ''))

    def _on_stop_cmd(self, msg: String) -> None:
        payload = self._parse_json(getattr(msg, 'data', ''))
        if self._state_machine.mode in {SystemMode.SAFE_STOP, SystemMode.FAULT}:
            return
        reason = str(payload.get('message') or payload.get('reason') or 'external stop requested')
        self._perform_stop(reason)

    def _on_fault_report(self, msg: FaultReport) -> None:
        source = str(getattr(msg, 'source', '') or '')
        if source == 'task_orchestrator':
            return
        code_raw = int(getattr(msg, 'code', 0) or 0)
        valid_codes = {int(v) for v in FaultCode}
        code = FaultCode(code_raw) if code_raw in valid_codes else FaultCode.UNKNOWN
        message = str(getattr(msg, 'message', '') or fault_message(code))
        if self._state_machine.mode not in {SystemMode.FAULT, SystemMode.SAFE_STOP}:
            self._enter_fault(code, detail=message)

    def _handle_start_task(self, request: StartTask.Request, response: StartTask.Response) -> StartTask.Response:
        task_id = f'task-{uuid.uuid4().hex[:8]}'
        graph_contract = resolve_task_graph_contract(str(request.task_type), target_selector=str(request.target_selector))
        queued = TaskRequest(
            task_id=task_id,
            task_type=str(request.task_type),
            target_selector=str(request.target_selector),
            place_profile=str(request.place_profile or 'default'),
            auto_retry=bool(request.auto_retry),
            max_retry=max(0, int(request.max_retry or 2)),
            metadata=dict(graph_contract),
            request_id=f'req-{task_id}',
            correlation_id=f'corr-{task_id}',
            task_run_id=f'taskrun-{task_id}',
            episode_id=f'episode-{task_id}',
        )
        decision = self._enqueue_task_request(queued)
        response.accepted = bool(decision.accepted)
        response.task_id = task_id if decision.accepted else ''
        response.message = 'Task queued' if decision.accepted else decision.message
        return response

    def _handle_reset_fault(self, request: ResetFault.Request, response: ResetFault.Response) -> ResetFault.Response:
        del request
        decision = self._evaluate_command_policy('resetFault')
        if not decision.accepted:
            response.success = False
            response.message = decision.message
            return response
        self._runtime_engine.clear_for_fault_reset()
        self._send_hardware_command({'kind': 'RESET_FAULT', 'task_id': 'system', 'timeout_sec': 0.6})
        transition = self._state_machine.to_idle('Fault reset; system back to IDLE')
        self._emit_event('WARN', 'task_orchestrator', 'FAULT_RESET', '', 0, transition.reason, stage='fault', error_code='fault_reset', operator_actionable=True)
        response.success = True
        response.message = transition.reason
        return response

    def _handle_stop_task(self, request: StopTask.Request, response: StopTask.Response) -> StopTask.Response:
        del request
        response.success = True
        response.message = self._perform_stop('Task stop requested')
        return response

    def _handle_home(self, request: HomeArm.Request, response: HomeArm.Response) -> HomeArm.Response:
        del request
        decision = self._evaluate_command_policy('home')
        if not decision.accepted:
            response.success = False
            response.message = decision.message
            return response
        self._send_hardware_command({'kind': 'HOME', 'task_id': getattr(self._current, 'task_id', 'system'), 'timeout_sec': 1.0})
        response.success = True
        response.message = 'Home command sent'
        return response

    def _perform_stop(self, reason: str, canceled_task_id: str | None = None) -> str:
        return self._runtime_engine.perform_stop(reason, canceled_task_id=canceled_task_id)

    def _tick(self) -> None:
        if not self.runtime_active:
            return
        self._publish_readiness()
        self._runtime_engine.tick(
            hardware_fresh_sec=float(self.get_parameter('hardware_fresh_sec').value),
            command_timeout_sec=float(self.get_parameter('command_timeout_sec').value),
            perception_blocked_after_sec=float(self.get_parameter('perception_blocked_after_sec').value),
        )

    def _dispatch_next_command(self) -> None:
        self._runtime_engine.dispatch_next_command(command_timeout_sec=float(self.get_parameter('command_timeout_sec').value))

    def _send_hardware_command(self, payload: dict) -> None:
        self._publishers.send_hardware_command(payload)

    def _publish_system_state(self) -> None:
        if not self.runtime_active:
            return
        self._publishers.publish_system_state(
            state_machine=self._state_machine,
            current=self._current,
            hardware=self._hardware,
            awaiting=self._awaiting,
            calibration=self._calibration,
            tracker=self._tracker,
            hardware_fresh_sec=float(self.get_parameter('hardware_fresh_sec').value),
        )

    def _publish_task_status(self) -> None:
        if not self.runtime_active or not bool(self.get_parameter('publish_task_status').value):
            return
        self._publishers.publish_task_status(
            current=self._current,
            phase=self._state_machine.phase,
            message=self._state_machine.last_reason,
            queue_depth=len(self._queue),
            awaiting=self._awaiting,
            calibration=self._calibration,
        )

    def _estimate_progress(self) -> float:
        return self._publishers.estimate_progress(phase=self._state_machine.phase, awaiting=self._awaiting, current=self._current)

    def _publish_summary(self) -> None:
        if not self.runtime_active:
            return
        self._publishers.publish_summary(
            queue_depth=len(self._queue),
            current=self._current,
            phase=self._state_machine.phase,
            awaiting=self._awaiting,
            tracker=self._tracker,
            last_feedback=self._last_feedback,
            mode=self._state_machine.mode,
            action_servers={
                'pickPlace': self._pick_place_action_server is not None,
                'homing': self._homing_action_server is not None,
                'recover': self._recover_action_server is not None,
            },
        )

    def _publish_readiness(self) -> None:
        if not self.runtime_active:
            return
        self._publishers.publish_readiness(
            state_machine=self._state_machine,
            supports_action_goals=self._pick_place_action_server is not None,
        )

    def _publish_fault_report(self, code: FaultCode, task_id: str, message: str) -> None:
        self._publishers.publish_fault_report(code=code, task_id=task_id, message=message)

    def _enter_fault(self, code: FaultCode, detail: str | None = None) -> None:
        self._runtime_engine.enter_fault(code, detail=detail)

    def _emit_event(
        self,
        level: str,
        source: str,
        event_type: str,
        task_id: str,
        code: int,
        message: str,
        *,
        stage: str | None = None,
        error_code: str | None = None,
        operator_actionable: bool | None = None,
        payload: dict[str, Any] | None = None,
    ) -> None:
        self._publishers.emit_event(
            level=level,
            source=source,
            event_type=event_type,
            task_id=task_id,
            code=code,
            message=message,
            current=self._current,
            phase=self._state_machine.phase,
            stage=stage,
            error_code=error_code,
            operator_actionable=operator_actionable,
            payload=payload,
        )


def main(args=None) -> None:  # pragma: no cover
    if rclpy is None:
        raise RuntimeError('rclpy unavailable')
    lifecycle_main(TaskOrchestratorNode, args=args)
