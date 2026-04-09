from __future__ import annotations

import json
import time
from typing import Any

try:
    import rclpy
    from rclpy.action import ActionClient, ActionServer, CancelResponse, GoalResponse
    from arm_backend_common.lifecycle_support import ManagedLifecycleNode, lifecycle_main
    from std_msgs.msg import String
    from arm_common import ActionNames, ActionTypes, MsgTypes, TopicNames

    HardwareState = MsgTypes.HardwareState
    FaultReport = MsgTypes.FaultReport
    try:
        from control_msgs.action import FollowJointTrajectory
        from trajectory_msgs.msg import JointTrajectory, JointTrajectoryPoint
        from builtin_interfaces.msg import Duration
    except Exception:  # pragma: no cover
        FollowJointTrajectory = JointTrajectory = JointTrajectoryPoint = Duration = object
except Exception:  # pragma: no cover
    rclpy = None
    ActionClient = ActionServer = object
    CancelResponse = GoalResponse = object
    ManagedLifecycleNode = object

    def lifecycle_main(factory, args=None):
        del factory, args
        raise RuntimeError('rclpy unavailable')

    String = object
    HardwareState = object
    FaultReport = object
    FollowJointTrajectory = JointTrajectory = JointTrajectoryPoint = Duration = object

    class TopicNames:
        READINESS_UPDATE = '/arm/readiness/update'
        MOTION_EXECUTOR_SUMMARY = '/arm/motion_executor/summary'
        INTERNAL_EXECUTE_PLAN = '/arm/internal/execute_plan'
        INTERNAL_EXECUTION_STATUS = '/arm/internal/execution_status'
        INTERNAL_HARDWARE_CMD = '/arm/internal/hardware_cmd'
        INTERNAL_ROS2_CONTROL_CMD = '/arm/internal/ros2_control_cmd'
        HARDWARE_STATE = '/arm/hardware/state'
        HARDWARE_FEEDBACK = '/arm/hardware/feedback'
        FAULT_REPORT = '/arm/fault/report'

    class ActionNames:
        HOME_SEQUENCE = '/arm/home_sequence'

    class _ActionTypes:
        HomeSequence = object

    ActionTypes = _ActionTypes()

from arm_backend_common.stage_plan import StagePlan
from arm_backend_common.safety_limits import SafetyLimits, SafetyViolation, load_safety_limits
from arm_common.runtime_contracts import build_execution_status
from .controller_adapter import ControllerAdapter
from .executor import MotionExecutor
from .transport_adapter import build_transport_adapter

HOME_ACTION_TIMEOUT_SEC = 2.0
HOME_ACTION_WAIT_STEP_SEC = 0.05
TERMINAL_EXECUTION_STATUSES = frozenset({'done', 'failed', 'timeout', 'canceled', 'fault'})


class MotionExecutorNode(ManagedLifecycleNode):
    def __init__(self) -> None:
        """Initialize runtime adapters and execution subscriptions.

        Functional behavior:
            - validates incoming stage plans
            - dispatches controller commands
            - optionally forwards commands to the hardware dispatcher when the
              selected runtime lane enables authoritative execution
            - consumes typed hardware state and typed fault reports from the
              shared ROS contract

        Returns:
            None.

        Raises:
            Does not raise directly. ROS initialization errors propagate from
            the underlying runtime when available.
        """
        super().__init__('motion_executor_node')
        self.declare_parameter('publish_period_sec', 1.0)
        self.declare_parameter('forward_hardware_commands', False)
        self.declare_parameter('hardware_execution_mode', 'protocol_bridge')
        self.declare_parameter('ros2_control_arm_action_name', '/arm_joint_trajectory_controller/follow_joint_trajectory')
        self.declare_parameter('ros2_control_gripper_action_name', '/gripper_command_controller/follow_joint_trajectory')
        self.declare_parameter('ros2_control_open_gripper_position', 0.04)
        self.declare_parameter('ros2_control_closed_gripper_position', 0.0)
        self.declare_parameter('ros2_control_default_time_from_start_sec', 0.8)
        self.declare_parameter('ros2_control_server_wait_timeout_sec', 0.2)
        self.declare_parameter('ros2_control_home_joint_names', ['joint_1', 'joint_2', 'joint_3', 'joint_4', 'joint_5', 'joint_6'])
        self.declare_parameter('ros2_control_home_joint_positions', [0.0, 0.0, 0.0, 0.0, 0.0, 0.0])
        self.declare_parameter('safety_limits_path', '')
        self._safety_limits = self._load_safety_limits()
        self._executor = MotionExecutor()
        self._controller = ControllerAdapter()
        self._pub = self.create_managed_publisher(String, TopicNames.READINESS_UPDATE, 10)
        self._summary = self.create_managed_publisher(String, TopicNames.MOTION_EXECUTOR_SUMMARY, 10)
        self._execution_status_pub = self.create_managed_publisher(String, TopicNames.INTERNAL_EXECUTION_STATUS, 20)
        self._hardware_cmd_pub = self.create_managed_publisher(String, TopicNames.INTERNAL_HARDWARE_CMD, 20)
        self._ros2_control_metadata_pub = self.create_managed_publisher(String, TopicNames.INTERNAL_ROS2_CONTROL_CMD, 20)
        self._ros2_control_arm_client = None
        self._ros2_control_gripper_client = None
        self._queued_commands: list[dict[str, Any]] = []
        self._create_ros2_control_clients()
        self._transport_adapter = build_transport_adapter(
            forward_hardware_commands=bool(self.get_parameter('forward_hardware_commands').value),
            execution_mode=str(self.get_parameter('hardware_execution_mode').value),
            publish_json=lambda payload: self._hardware_cmd_pub.publish(String(data=payload)),
            submit_ros2_control_command=self._submit_ros2_control_command,
        )
        self._last_execution: dict[str, Any] = {'status': 'idle', 'expectedStages': list(self._executor.STAGE_ORDER), 'transportMode': self._transport_adapter.transport_mode(), 'hardwareExecutionMode': self._transport_adapter.execution_mode}
        self._active_runtime_request: dict[str, Any] = {}
        self.create_subscription(String, TopicNames.INTERNAL_EXECUTE_PLAN, self._on_execute_plan, 20)
        self.create_subscription(String, TopicNames.HARDWARE_FEEDBACK, self._on_hardware_feedback, 20)
        self.create_subscription(HardwareState, TopicNames.HARDWARE_STATE, self._on_hardware_state, 20)
        self.create_subscription(FaultReport, TopicNames.FAULT_REPORT, self._on_fault_report, 20)
        self._home_sequence_action_server = None
        self._create_action_servers()
        self.create_timer(float(self.get_parameter('publish_period_sec').value), self._publish_status)


    def _load_safety_limits(self) -> SafetyLimits:
        """Load runtime safety limits from the configured authority file."""
        configured_path = ''
        try:
            configured_path = str(self.get_parameter('safety_limits_path').value or '').strip()
        except Exception:
            configured_path = ''
        return load_safety_limits(configured_path or None)

    def _active_safety_limits(self) -> SafetyLimits:
        limits = getattr(self, '_safety_limits', None)
        if isinstance(limits, SafetyLimits):
            return limits
        limits = MotionExecutorNode._load_safety_limits(self)
        try:
            self._safety_limits = limits
        except Exception:
            pass
        return limits

    def _validate_command_against_safety(self, command: dict[str, Any]) -> None:
        """Validate one executor command against the runtime safety authority.

        Args:
            command: Serialized execution command destined for transport dispatch.

        Returns:
            None.

        Raises:
            SafetyViolation: If the command violates configured runtime limits.
        """
        if not isinstance(command, dict):
            raise SafetyViolation('executor command must be a dictionary')
        limits = MotionExecutorNode._active_safety_limits(self)
        kind = str(command.get('kind', '') or '')
        target = command.get('execution_target')
        if isinstance(target, dict) and target:
            limits.require_execution_target(target, context=f'motion_executor {kind or "command"}')
        force = command.get('force')
        if force is not None:
            limits.require_gripper_force(float(force), context=f'motion_executor {kind or "command"}')

    def _reject_command_for_safety(self, command: dict[str, Any], *, message: str) -> None:
        handle = self._executor.dispatch_stage(command, started_monotonic=time.monotonic())
        failure = self._executor.mark_failed(handle.command_id, message=message, source='safety_limits', status='failed')
        self._controller.accept_feedback({
            'command_id': failure.command_id,
            'status': 'failed',
            'source': 'safety_limits',
            'message': message,
            'result_code': 'safety_limits',
            'execution_state': 'failed',
        })
        setattr(self, '_queued_commands', [])
        self._last_execution['status'] = 'failed'
        self._last_execution['hardwareCommandForwarding'] = False
        self._last_execution['transportMode'] = self._transport_adapter.transport_mode()
        self._last_execution['hardwareExecutionMode'] = self._transport_adapter.execution_mode
        self._last_execution['transportMessages'] = [message]
        self._last_execution['commandId'] = failure.command_id
        self._last_execution['stageName'] = failure.stage_name
        self._publish_active_terminal_status(
            status='failed',
            message=message,
            stage_name=failure.stage_name or str(command.get('stage', '')),
            command_id=failure.command_id or str(command.get('command_id', '')),
        )

    def _create_action_servers(self) -> None:
        if ActionServer is object:
            return
        home_sequence_action = getattr(ActionTypes, 'HomeSequence', object)
        if home_sequence_action is not object:
            self._home_sequence_action_server = ActionServer(
                self,
                home_sequence_action,
                ActionNames.HOME_SEQUENCE,
                execute_callback=self._execute_home_sequence_action,
                goal_callback=lambda _goal: GoalResponse.ACCEPT,
                cancel_callback=lambda _goal: CancelResponse.ACCEPT,
            )


    def _create_ros2_control_clients(self) -> None:
        if ActionClient is object or FollowJointTrajectory is object:
            return
        self._ros2_control_arm_client = ActionClient(
            self,
            FollowJointTrajectory,
            str(self.get_parameter('ros2_control_arm_action_name').value),
        )
        self._ros2_control_gripper_client = ActionClient(
            self,
            FollowJointTrajectory,
            str(self.get_parameter('ros2_control_gripper_action_name').value),
        )

    def _sequential_transport_enabled(self) -> bool:
        checker = getattr(self._transport_adapter, 'requires_sequential_dispatch', None)
        return bool(checker()) if callable(checker) else False

    @staticmethod
    def _seconds_to_duration(seconds: float):
        seconds = max(0.0, float(seconds or 0.0))
        if Duration is object:
            return {'sec': int(seconds), 'nanosec': int(round((seconds - int(seconds)) * 1_000_000_000))}
        whole = int(seconds)
        nanosec = int(round((seconds - whole) * 1_000_000_000))
        return Duration(sec=whole, nanosec=nanosec)

    def _home_execution_target(self) -> dict[str, Any]:
        joint_names = [str(item) for item in list(self.get_parameter('ros2_control_home_joint_names').value or [])]
        positions = [float(item) for item in list(self.get_parameter('ros2_control_home_joint_positions').value or [])]
        if len(joint_names) != len(positions) or not joint_names:
            raise ValueError('ros2_control home joint configuration must contain aligned joint names and positions')
        target = {
            'controller': 'arm',
            'joint_names': joint_names,
            'points': [{'positions': positions, 'time_from_start_sec': float(self.get_parameter('ros2_control_default_time_from_start_sec').value)}],
        }
        MotionExecutorNode._active_safety_limits(self).require_execution_target(target, context='ros2_control home target')
        return target

    def _normalize_ros2_control_execution_target(self, command: dict[str, Any]) -> dict[str, Any]:
        target = dict(command.get('execution_target') or {})
        kind = str(command.get('kind', '') or '')
        if kind == 'HOME' and not target:
            target = self._home_execution_target()
        if kind in {'OPEN_GRIPPER', 'CLOSE_GRIPPER'} and not target:
            target = {
                'controller': 'gripper',
                'joint_names': ['gripper_joint'],
                'points': [{
                    'positions': [
                        float(self.get_parameter('ros2_control_open_gripper_position').value)
                        if kind == 'OPEN_GRIPPER'
                        else float(self.get_parameter('ros2_control_closed_gripper_position').value)
                    ],
                    'time_from_start_sec': float(self.get_parameter('ros2_control_default_time_from_start_sec').value),
                }],
            }
        if not target:
            raise ValueError('ros2_control execution requires execution_target metadata')
        target.setdefault('controller', 'arm')
        MotionExecutorNode._active_safety_limits(self).require_execution_target(target, context=f'ros2_control {kind or "command"}')
        return target

    def _build_joint_trajectory(self, target: dict[str, Any]):
        if JointTrajectory is object or JointTrajectoryPoint is object:
            raise RuntimeError('trajectory message types unavailable')
        trajectory = JointTrajectory()
        trajectory.joint_names = [str(name) for name in list(target.get('joint_names') or [])]
        points = []
        for item in list(target.get('points') or []):
            point = JointTrajectoryPoint()
            point.positions = [float(value) for value in list(item.get('positions') or [])]
            point.velocities = [float(value) for value in list(item.get('velocities') or [])] if item.get('velocities') is not None else []
            point.accelerations = [float(value) for value in list(item.get('accelerations') or [])] if item.get('accelerations') is not None else []
            point.time_from_start = self._seconds_to_duration(float(item.get('time_from_start_sec', 0.0) or 0.0))
            points.append(point)
        trajectory.points = points
        return trajectory

    @staticmethod
    def _ros2_control_client_ready(client: Any, controller: str, *, timeout_sec: float) -> tuple[bool, str]:
        """Validate one ros2_control action client before live dispatch.

        Args:
            client: Action client bound to the target controller.
            controller: Stable controller label used in diagnostics.
            timeout_sec: Maximum wait-for-server budget in seconds.

        Returns:
            tuple[bool, str]: Readiness flag and a stable detail string.

        Raises:
            Does not raise. Failures are converted into fail-closed detail codes.

        Boundary behavior:
            Missing clients, missing ``wait_for_server`` support, or timeout
            expiration all degrade to ``False`` so live execution never promotes
            on partial controller availability.
        """
        normalized_controller = str(controller or 'arm').strip() or 'arm'
        if client is None:
            return False, f'ros2_control_action_client_unavailable:{normalized_controller}'
        wait_for_server = getattr(client, 'wait_for_server', None)
        if not callable(wait_for_server):
            return False, f'ros2_control_wait_for_server_missing:{normalized_controller}'
        if not bool(wait_for_server(timeout_sec=max(0.0, float(timeout_sec or 0.0)))):
            return False, f'ros2_control_controller_unavailable:{normalized_controller}'
        return True, f'ros2_control_controller_ready:{normalized_controller}'

    def _ros2_control_runtime_ready(self) -> tuple[bool, str]:
        """Return whether the live ros2_control execution backbone is ready.

        Args:
            None.

        Returns:
            tuple[bool, str]: Overall readiness flag and a stable detail string.

        Raises:
            Does not raise.

        Boundary behavior:
            Non-live execution modes report executor readiness immediately. The
            validated-live lane requires both arm and gripper controllers to be
            reachable before ``motion_executor`` is published as ready.
        """
        if str(self._transport_adapter.execution_mode) != 'ros2_control_live':
            return True, 'executor_ready'
        timeout_sec = float(self.get_parameter('ros2_control_server_wait_timeout_sec').value)
        arm_ready, arm_detail = self._ros2_control_client_ready(self._ros2_control_arm_client, 'arm', timeout_sec=timeout_sec)
        if not arm_ready:
            return False, arm_detail
        gripper_ready, gripper_detail = self._ros2_control_client_ready(self._ros2_control_gripper_client, 'gripper', timeout_sec=timeout_sec)
        if not gripper_ready:
            return False, gripper_detail
        return True, 'ros2_control_backbone_ready'

    def _submit_ros2_control_command(self, command: dict[str, Any]) -> tuple[bool, str]:
        try:
            target = self._normalize_ros2_control_execution_target(command)
            controller = str(target.get('controller', 'arm') or 'arm')
            client = self._ros2_control_gripper_client if controller == 'gripper' else self._ros2_control_arm_client
            ready, detail = self._ros2_control_client_ready(
                client,
                controller,
                timeout_sec=float(self.get_parameter('ros2_control_server_wait_timeout_sec').value),
            )
            if not ready:
                return False, detail
            goal = FollowJointTrajectory.Goal()
            goal.trajectory = self._build_joint_trajectory(target)
            metadata = {
                'command_id': str(command.get('command_id', '') or ''),
                'plan_id': str(command.get('plan_id', '') or ''),
                'task_id': str(command.get('task_id', '') or ''),
                'stage': str(command.get('stage', '') or ''),
                'kind': str(command.get('kind', '') or ''),
                'request_id': str(command.get('request_id', command.get('requestId', '')) or ''),
                'correlation_id': str(command.get('correlation_id', command.get('correlationId', '')) or ''),
                'task_run_id': str(command.get('task_run_id', command.get('taskRunId', '')) or ''),
                'execution_mode': str(command.get('execution_mode', self._transport_adapter.execution_mode) or ''),
                'transport_contract': 'ros2_control_live_v1',
                'controller': controller,
                'execution_target': target,
            }
            self._ros2_control_metadata_pub.publish(String(data=json.dumps(metadata, ensure_ascii=False)))
            send_future = client.send_goal_async(goal)
            send_future.add_done_callback(lambda future, metadata=metadata: self._on_ros2_control_goal_response(future, metadata))
            return True, f'command submitted to ros2_control {controller} controller'
        except Exception as exc:
            return False, f'ros2_control submission failed: {exc}'

    def _on_ros2_control_goal_response(self, future, metadata: dict[str, Any]) -> None:
        try:
            goal_handle = future.result()
        except Exception as exc:  # pragma: no cover
            self._accept_transport_feedback({**metadata, 'status': 'failed', 'source': 'ros2_control', 'message': f'goal submission failed: {exc}', 'result_code': 'goal_submission_failed', 'execution_state': 'failed'})
            return
        if goal_handle is None or not bool(getattr(goal_handle, 'accepted', False)):
            self._accept_transport_feedback({**metadata, 'status': 'failed', 'source': 'ros2_control', 'message': 'ros2_control goal rejected', 'result_code': 'goal_rejected', 'execution_state': 'failed'})
            return
        self._accept_transport_feedback({**metadata, 'status': 'ack', 'source': 'ros2_control', 'message': 'ros2_control goal accepted', 'result_code': 'accepted', 'execution_state': 'accepted'})
        result_future = goal_handle.get_result_async()
        result_future.add_done_callback(lambda result_future, metadata=metadata: self._on_ros2_control_goal_result(result_future, metadata))

    def _on_ros2_control_goal_result(self, future, metadata: dict[str, Any]) -> None:
        try:
            wrapped = future.result()
            result = getattr(wrapped, 'result', wrapped)
            error_code = int(getattr(result, 'error_code', 0))
            error_string = str(getattr(result, 'error_string', '') or '')
        except Exception as exc:  # pragma: no cover
            self._accept_transport_feedback({**metadata, 'status': 'failed', 'source': 'ros2_control', 'message': f'ros2_control result unavailable: {exc}', 'result_code': 'result_unavailable', 'execution_state': 'failed'})
            return
        if error_code == 0:
            self._accept_transport_feedback({**metadata, 'status': 'done', 'source': 'ros2_control', 'message': 'ros2_control trajectory completed', 'result_code': 'success', 'execution_state': 'succeeded'})
            return
        self._accept_transport_feedback({**metadata, 'status': 'failed', 'source': 'ros2_control', 'message': error_string or f'ros2_control trajectory failed ({error_code})', 'result_code': str(error_code), 'execution_state': 'failed'})

    def _publish_execution_status(self, payload: dict[str, Any]) -> None:
        """Publish one execution-status payload on the shared JSON channel.

        Args:
            payload: Serialized execution contract.

        Returns:
            None.

        Raises:
            Does not raise. Transport failures are delegated to ROS middleware.
        """
        self._execution_status_pub.publish(String(data=json.dumps(payload, ensure_ascii=False)))

    def _check_execution_timeouts(self) -> None:
        if not self._active_runtime_request:
            return
        state = getattr(self._executor, '_state', None)
        handles = getattr(state, 'handles', {}) if state is not None else {}
        for command_id, handle in list(handles.items()):
            if handle.result_status in TERMINAL_EXECUTION_STATUSES:
                continue
            if handle.timeout_sec > 0.0 and handle.started_monotonic > 0.0 and (time.monotonic() - handle.started_monotonic) > handle.timeout_sec:
                result = self._executor.mark_timeout(command_id, source='motion_executor_node')
                self._last_execution = {
                    'status': result.status,
                    'taskId': self._active_runtime_request.get('taskId', ''),
                    'message': result.message,
                    'commandId': result.command_id,
                    'stageName': result.stage_name,
                }
                self._publish_execution_status(build_execution_status(
                    request_id=str(self._active_runtime_request.get('requestId', '')),
                    task_id=str(self._active_runtime_request.get('taskId', '')),
                    status='timeout',
                    message=result.message,
                    stage_name=result.stage_name,
                    command_id=result.command_id,
                    correlation_id=str(self._active_runtime_request.get('correlationId', '')),
                    task_run_id=str(self._active_runtime_request.get('taskRunId', '')),
                ))
                setattr(self, '_queued_commands', [])
                self._active_runtime_request = {}
                return

    def _publish_status(self) -> None:
        if not self.runtime_active:
            return
        self._check_execution_timeouts()
        readiness_ok, readiness_detail = self._ros2_control_runtime_ready()
        self._pub.publish(String(data=json.dumps({'check': 'motion_executor', 'ok': readiness_ok, 'detail': readiness_detail, 'staleAfterSec': 2.5}, ensure_ascii=False)))
        payload = {
            **self._last_execution,
            'expectedStages': list(self._executor.STAGE_ORDER),
            'executionState': self._executor.snapshot(),
            'controllerState': self._controller.read_state(),
            'transportState': self._transport_adapter.snapshot(),
            'readinessOk': readiness_ok,
            'readinessDetail': readiness_detail,
            'updatedAt': round(time.time(), 3),
        }
        self._summary.publish(String(data=json.dumps(payload, ensure_ascii=False)))

    def _await_terminal_execution(self, command_id: str, *, timeout_sec: float) -> dict[str, str]:
        """Wait for a dispatched command to reach a terminal execution state.

        Args:
            command_id: Stable command identifier.
            timeout_sec: Maximum wait duration.

        Returns:
            dict[str, str]: Execution status, stage name, and detail message.

        Raises:
            ValueError: If ``command_id`` is empty or ``timeout_sec`` is invalid.
        """
        if not str(command_id).strip():
            raise ValueError('command_id must be non-empty')
        if timeout_sec <= 0.0:
            raise ValueError('timeout_sec must be positive')
        deadline = time.monotonic() + timeout_sec
        while time.monotonic() < deadline:
            state = self._executor.snapshot()
            handle = (state.get('handles') or {}).get(command_id) or {}
            status = str(handle.get('resultStatus', handle.get('status', ''))).strip()
            if status in TERMINAL_EXECUTION_STATUSES:
                return {
                    'status': status,
                    'stageName': str(handle.get('stageName', '')),
                    'message': str(handle.get('message', status)),
                    'feedbackSource': str(handle.get('feedbackSource', '')),
                }
            time.sleep(HOME_ACTION_WAIT_STEP_SEC)
        timeout_result = self._executor.mark_timeout(command_id, source='home_sequence_action')
        self._controller.accept_feedback({
            'command_id': command_id,
            'status': 'timeout',
            'source': 'home_sequence_action',
            'message': timeout_result.message,
        })
        return {
            'status': timeout_result.status,
            'stageName': timeout_result.stage_name,
            'message': timeout_result.message,
            'feedbackSource': timeout_result.feedback_source,
        }

    def _dispatch_one_command(self, command: dict[str, Any]) -> TransportDispatchResult | None:
        try:
            MotionExecutorNode._validate_command_against_safety(self, command)
        except SafetyViolation as exc:
            self._reject_command_for_safety(command, message=str(exc))
            return None
        self._executor.dispatch_stage(command, started_monotonic=time.monotonic())
        self._controller.send_command(command)
        transport_result = self._transport_adapter.dispatch(command)
        if not transport_result.accepted:
            failure = self._executor.mark_failed(
                str(command.get('command_id', '')),
                message=transport_result.message,
                source='transport_adapter',
                status='failed',
            )
            self._controller.accept_feedback({
                'command_id': str(command.get('command_id', '')),
                'status': 'failed',
                'source': 'transport_adapter',
                'message': transport_result.message,
                'result_code': 'transport_rejected',
                'execution_state': 'failed',
            })
            setattr(self, '_queued_commands', [])
            self._last_execution['status'] = 'failed'
            self._last_execution['hardwareCommandForwarding'] = False
            self._last_execution['transportMode'] = self._transport_adapter.transport_mode()
            self._last_execution['hardwareExecutionMode'] = self._transport_adapter.execution_mode
            self._last_execution['transportMessages'] = [transport_result.message]
            self._last_execution['commandId'] = failure.command_id
            self._last_execution['stageName'] = failure.stage_name
            self._publish_active_terminal_status(
                status='failed',
                message=transport_result.message,
                stage_name=failure.stage_name or str(command.get('stage', '')),
                command_id=failure.command_id or str(command.get('command_id', '')),
            )
            return None
        self._last_execution['status'] = 'forwarded' if transport_result.forwarded else 'shadowed'
        self._last_execution['hardwareCommandForwarding'] = transport_result.forwarded
        self._last_execution['transportMode'] = self._transport_adapter.transport_mode()
        self._last_execution['hardwareExecutionMode'] = self._transport_adapter.execution_mode
        return transport_result

    def _dispatch_next_queued_command(self) -> None:
        if not self._queued_commands:
            return
        command = dict(self._queued_commands.pop(0))
        transport_result = self._dispatch_one_command(command)
        if transport_result is None:
            return
        self._last_execution['transportMessages'] = [transport_result.message]
        self._last_execution['queuedCommandsRemaining'] = len(self._queued_commands)
        self._last_execution['sequentialDispatch'] = True
        self._last_execution['commandId'] = str(command.get('command_id', ''))
        self._last_execution['stageName'] = str(command.get('stage', ''))

    def _dispatch_commands(self, commands: list[dict[str, Any]]) -> None:
        """Dispatch validated commands into controller state and runtime transport.

        Args:
            commands: Validated command stream returned by :class:`MotionExecutor`.

        Returns:
            None.

        Raises:
            Does not raise. Dispatch errors are converted into execution-state failures.
        """
        if self._sequential_transport_enabled():
            self._queued_commands = [dict(item) for item in commands]
            self._dispatch_next_queued_command()
            return
        forwarded_any = False
        dispatch_messages: list[str] = []
        for command in commands:
            transport_result = self._dispatch_one_command(command)
            if transport_result is None:
                return
            dispatch_messages.append(transport_result.message)
            forwarded_any = forwarded_any or transport_result.forwarded
        self._last_execution['status'] = 'forwarded' if forwarded_any else 'shadowed'
        self._last_execution['hardwareCommandForwarding'] = forwarded_any
        self._last_execution['transportMode'] = self._transport_adapter.transport_mode()
        self._last_execution['hardwareExecutionMode'] = self._transport_adapter.execution_mode
        self._last_execution['transportMessages'] = dispatch_messages
        self._last_execution['sequentialDispatch'] = False

    def _on_execute_plan(self, msg: String) -> None:
        if not self.runtime_active:
            self._last_execution = {'status': 'inactive', 'message': 'motion executor inactive'}
            return
        payload = self._parse_json(msg.data)
        request_id = str(payload.get('requestId', ''))
        correlation_id = str(payload.get('correlationId', ''))
        task_run_id = str(payload.get('taskRunId', ''))
        task_id = str(payload.get('task_id', 'executor-preview'))
        raw_stages = payload.get('stages') or []
        stages = [StagePlan(str(item.get('name', '')), str(item.get('kind', '')), dict(item.get('payload') or {})) for item in raw_stages if isinstance(item, dict)]
        validation = self._executor.validate(stages)
        if not validation.accepted:
            self._last_execution = {'status': 'rejected', 'taskId': task_id, 'message': validation.message, 'stageCount': validation.stage_count}
            self._publish_execution_status(build_execution_status(
                request_id=request_id,
                task_id=task_id,
                status='rejected',
                message=validation.message,
                correlation_id=correlation_id,
                task_run_id=task_run_id,
            ))
            return
        commands = self._executor.build_command_stream(
            stages,
            task_id,
            request_metadata={
                'request_id': request_id,
                'correlation_id': correlation_id,
                'task_run_id': task_run_id,
            },
        )
        self._active_runtime_request = {'requestId': request_id, 'taskId': task_id, 'correlationId': correlation_id, 'taskRunId': task_run_id}
        self._last_execution = {
            'status': 'validated',
            'taskId': task_id,
            'message': validation.message,
            'stageCount': validation.stage_count,
            'commandCount': len(commands),
            'planId': commands[0].get('plan_id') if commands else '',
        }
        if not commands:
            self._publish_execution_status(build_execution_status(
                request_id=request_id,
                task_id=task_id,
                status='rejected',
                message='empty command stream',
                correlation_id=correlation_id,
                task_run_id=task_run_id,
            ))
            self._active_runtime_request = {}
            return
        self._dispatch_commands(commands)


    def _active_request_field(self, name: str) -> str:
        """Return one normalized field from the active runtime request.

        Args:
            name: Canonical field name.

        Returns:
            str: Normalized field value or an empty string when unavailable.

        Raises:
            Does not raise.
        """
        return str(self._active_runtime_request.get(name, '') or '')

    def _publish_active_terminal_status(self, *, status: str, message: str, stage_name: str = '', command_id: str = '') -> None:
        """Publish one terminal execution status for the active request.

        Args:
            status: Terminal business-level status.
            message: Human-readable terminal detail.
            stage_name: Optional stage name.
            command_id: Optional correlated command identifier.

        Returns:
            None.

        Raises:
            Does not raise.
        """
        if not self._active_runtime_request:
            return
        self._publish_execution_status(build_execution_status(
            request_id=self._active_request_field('requestId'),
            task_id=self._active_request_field('taskId'),
            status=status,
            message=message,
            stage_name=stage_name,
            command_id=command_id,
            correlation_id=self._active_request_field('correlationId'),
            task_run_id=self._active_request_field('taskRunId'),
        ))
        self._active_runtime_request = {}

    def _mark_executor_fault(self, *, message: str, source: str, stage_name: str = '', command_id: str = '') -> tuple[str, str]:
        """Convert runtime faults into terminal executor failures.

        Args:
            message: Failure detail copied onto all active handles.
            source: Reporting component.
            stage_name: Optional fallback stage name when no active handle exists.
            command_id: Optional fallback command identifier.

        Returns:
            tuple[str, str]: Terminal stage name and command identifier chosen
            for publishing business-level failure status.

        Raises:
            Does not raise.
        """
        if command_id:
            result = self._executor.mark_failed(command_id, message=message, source=source, status='failed')
            terminal_stage = result.stage_name or stage_name
            terminal_command = result.command_id or command_id
            self._executor.mark_all_failed(message=message, source=source, status='failed')
            return terminal_stage, terminal_command
        results = self._executor.mark_all_failed(message=message, source=source, status='failed')
        if results:
            terminal = results[0]
            return terminal.stage_name, terminal.command_id
        return stage_name, command_id

    def _accept_transport_feedback(self, feedback: dict[str, Any]) -> None:
        if not feedback:
            return
        try:
            controller_feedback = self._controller.accept_feedback(feedback)
            result = self._executor.accept_feedback(feedback)
        except ValueError as exc:
            self._last_execution = {
                'status': 'failed',
                'message': str(exc),
                'invalidFeedback': feedback,
            }
            setattr(self, '_queued_commands', [])
            if self._active_runtime_request:
                self._publish_active_terminal_status(
                    status='failed',
                    message=str(exc),
                    stage_name=str(feedback.get('stage', '')),
                    command_id=str(feedback.get('command_id', '')),
                )
            return
        snapshot = self._executor.snapshot()
        public_status = 'failed' if result.status == 'fault' else result.status
        queued_commands = list(getattr(self, '_queued_commands', []) or [])
        sequential_dispatch_enabled = bool(getattr(self, '_sequential_transport_enabled', lambda: False)())
        self._last_execution = {
            'status': public_status,
            'rawStatus': result.status,
            'taskId': snapshot.get('taskId', ''),
            'message': result.message,
            'commandId': result.command_id,
            'stageName': result.stage_name,
            'feedbackSource': result.feedback_source,
            'controllerFeedback': controller_feedback,
            'queuedCommandsRemaining': len(queued_commands),
            'sequentialDispatch': sequential_dispatch_enabled,
        }
        if not self._active_runtime_request:
            return
        handles = list((snapshot.get('handles') or {}).values())
        handle_statuses = {str(item.get('resultStatus', '')) for item in handles}
        if result.status in {'failed', 'timeout', 'canceled', 'fault'}:
            setattr(self, '_queued_commands', [])
            terminal_stage = result.stage_name
            terminal_command = result.command_id
            terminal_message = result.message
            terminal_status = result.status
            if result.status == 'fault':
                terminal_stage, terminal_command = self._mark_executor_fault(
                    message=result.message or 'hardware fault',
                    source=result.feedback_source or 'hardware_feedback',
                    stage_name=result.stage_name,
                    command_id=result.command_id,
                )
                terminal_status = 'failed'
                terminal_message = result.message or 'hardware fault'
            self._publish_active_terminal_status(
                status=terminal_status,
                message=terminal_message,
                stage_name=terminal_stage,
                command_id=terminal_command,
            )
            return
        if result.status == 'done' and sequential_dispatch_enabled and queued_commands:
            dispatch_next = getattr(self, '_dispatch_next_queued_command', None)
            if callable(dispatch_next):
                dispatch_next()
            return
        if handles and handle_statuses == {'done'}:
            setattr(self, '_queued_commands', [])
            self._publish_active_terminal_status(
                status='done',
                message='execution finished',
                stage_name=result.stage_name,
                command_id=result.command_id,
            )

    def _on_hardware_feedback(self, msg: String) -> None:
        feedback = self._parse_json(msg.data)
        if not feedback:
            return
        handler = getattr(self, '_accept_transport_feedback', None)
        if callable(handler):
            handler(feedback)
            return
        MotionExecutorNode._accept_transport_feedback(self, feedback)

    def _on_hardware_state(self, msg: HardwareState) -> None:
        """Consume the typed hardware-state contract published by the aggregator.

        Args:
            msg: Typed ``HardwareState`` message.

        Returns:
            None.

        Boundary behavior:
            Invalid or absent ``raw_status`` payload falls back to the typed fields
            so executor summaries remain populated even when the JSON mirror drifts.
        """
        state = self._parse_json(getattr(msg, 'raw_status', ''))
        if not state:
            state = {
                'stm32_online': bool(getattr(msg, 'stm32_online', False)),
                'esp32_online': bool(getattr(msg, 'esp32_online', False)),
                'motion_busy': bool(getattr(msg, 'motion_busy', False)),
                'home_ok': bool(getattr(msg, 'home_ok', False)),
                'gripper_ok': bool(getattr(msg, 'gripper_ok', False)),
                'hardware_fault_code': int(getattr(msg, 'hardware_fault_code', 0)),
            }
        self._last_execution['hardwareState'] = state

    def _on_fault_report(self, msg: FaultReport) -> None:
        """Convert typed fault reports into executor failure state.

        Args:
            msg: Typed ``FaultReport`` message.

        Returns:
            None.

        Raises:
            Does not raise.
        """
        fault = {
            'code': int(getattr(msg, 'code', 0)),
            'source': str(getattr(msg, 'source', '')),
            'severity': str(getattr(msg, 'severity', '')),
            'task_id': str(getattr(msg, 'task_id', '')),
            'message': str(getattr(msg, 'message', 'system fault')),
        }
        stage_name, command_id = self._mark_executor_fault(
            message=fault['message'],
            source=fault['source'] or 'fault_report',
        )
        self._last_execution = {'status': 'failed', 'message': fault['message'], 'fault': fault, 'stageName': stage_name, 'commandId': command_id}
        self._publish_active_terminal_status(
            status='failed',
            message=fault['message'],
            stage_name=stage_name,
            command_id=command_id,
        )

    async def _execute_home_sequence_action(self, goal_handle):
        """Execute the home-sequence action and wait for terminal feedback.

        Args:
            goal_handle: ROS action goal handle.

        Returns:
            ActionTypes.HomeSequence.Result: Action result payload.

        Raises:
            Does not raise directly. Transport errors are converted into action
            result messages and timeout states.
        """
        sequential_dispatch_enabled = bool(getattr(self, '_sequential_transport_enabled', lambda: False)())
        home_execution_target_factory = getattr(self, '_home_execution_target', lambda: {})
        command = {
            'kind': 'HOME',
            'task_id': 'executor-home-sequence',
            'timeout_sec': 1.0,
            'command_id': 'executor-home-sequence:1:go_home',
            'plan_id': 'home-sequence',
            'stage': 'go_home',
            'execution_target': home_execution_target_factory() if sequential_dispatch_enabled else {},
        }
        self._executor.dispatch_stage(command, started_monotonic=time.monotonic())
        self._controller.send_command(command)
        transport_result = self._transport_adapter.dispatch(command)
        self._last_execution = {
            'status': 'forwarded' if transport_result.forwarded else 'shadowed',
            'command': command,
            'transportMode': transport_result.transport_mode,
            'hardwareExecutionMode': transport_result.execution_mode,
            'hardwareCommandForwarding': transport_result.forwarded,
            'transportMessages': [transport_result.message],
        }
        feedback = ActionTypes.HomeSequence.Feedback()
        feedback.stage = 'go_home'
        feedback.progress = 0.5
        goal_handle.publish_feedback(feedback)
        terminal = self._await_terminal_execution(command['command_id'], timeout_sec=max(float(command['timeout_sec']), HOME_ACTION_TIMEOUT_SEC))
        result = ActionTypes.HomeSequence.Result()
        result.accepted = terminal['status'] == 'done'
        result.message = terminal['message'] or terminal['status']
        self._last_execution = {'status': terminal['status'], 'command': command, 'feedbackSource': terminal['feedbackSource']}
        feedback.stage = terminal['stageName'] or 'go_home'
        feedback.progress = 1.0 if terminal['status'] == 'done' else 0.0
        goal_handle.publish_feedback(feedback)
        if terminal['status'] == 'done':
            goal_handle.succeed()
        else:
            goal_handle.abort()
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
    lifecycle_main(MotionExecutorNode, args=args)
