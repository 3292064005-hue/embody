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
        MOTION_EXECUTOR_SUMMARY = '/arm/motion_executor/summary'
        INTERNAL_EXECUTE_PLAN = '/arm/internal/execute_plan'
        INTERNAL_EXECUTION_STATUS = '/arm/internal/execution_status'
        INTERNAL_HARDWARE_CMD = '/arm/internal/hardware_cmd'
        HARDWARE_STATE = '/arm/hardware/state'
        HARDWARE_FEEDBACK = '/arm/hardware/feedback'
        SYSTEM_FAULT = '/arm/system/fault'

    class ActionNames:
        HOME_SEQUENCE = '/arm/home_sequence'

    class _ActionTypes:
        HomeSequence = object

    ActionTypes = _ActionTypes()

from arm_backend_common.stage_plan import StagePlan
from arm_common.runtime_contracts import build_execution_status
from .controller_adapter import ControllerAdapter
from .executor import MotionExecutor

HOME_ACTION_TIMEOUT_SEC = 2.0
HOME_ACTION_WAIT_STEP_SEC = 0.05
TERMINAL_EXECUTION_STATUSES = frozenset({'done', 'failed', 'timeout', 'canceled'})


class MotionExecutorNode(ManagedLifecycleNode):
    def __init__(self) -> None:
        """Initialize publishers, subscriptions, adapters, and action servers.

        Args:
            None.

        Returns:
            None.

        Raises:
            Does not raise directly. ROS initialization errors propagate from
            the underlying runtime when available.
        """
        super().__init__('motion_executor_node')
        self.declare_parameter('publish_period_sec', 1.0)
        self.declare_parameter('forward_hardware_commands', False)
        self._executor = MotionExecutor()
        self._controller = ControllerAdapter()
        self._pub = self.create_managed_publisher(String, TopicNames.READINESS_UPDATE, 10)
        self._summary = self.create_managed_publisher(String, TopicNames.MOTION_EXECUTOR_SUMMARY, 10)
        self._execution_status_pub = self.create_managed_publisher(String, TopicNames.INTERNAL_EXECUTION_STATUS, 20)
        self._hardware_cmd_pub = self.create_managed_publisher(String, TopicNames.INTERNAL_HARDWARE_CMD, 20)
        self._last_execution = {'status': 'idle', 'expectedStages': list(self._executor.STAGE_ORDER)}
        self._active_runtime_request: dict[str, Any] = {}
        self.create_subscription(String, TopicNames.INTERNAL_EXECUTE_PLAN, self._on_execute_plan, 20)
        self.create_subscription(String, TopicNames.HARDWARE_FEEDBACK, self._on_hardware_feedback, 20)
        self.create_subscription(String, TopicNames.HARDWARE_STATE, self._on_hardware_state, 20)
        self.create_subscription(String, TopicNames.SYSTEM_FAULT, self._on_system_fault, 20)
        self._home_sequence_action_server = None
        self._create_action_servers()
        self.create_timer(float(self.get_parameter('publish_period_sec').value), self._publish_status)

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

    def _publish_execution_status(self, payload: dict[str, Any]) -> None:
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
                self._last_execution = {'status': result.status, 'taskId': self._active_runtime_request.get('taskId', ''), 'message': result.message, 'commandId': result.command_id, 'stageName': result.stage_name}
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
                self._active_runtime_request = {}
                return

    def _publish_status(self) -> None:
        if not self.runtime_active:
            return
        self._check_execution_timeouts()
        self._pub.publish(String(data=json.dumps({'check': 'motion_executor', 'ok': True, 'detail': 'executor_ready', 'staleAfterSec': 2.5}, ensure_ascii=False)))
        payload = {**self._last_execution, 'expectedStages': list(self._executor.STAGE_ORDER), 'executionState': self._executor.snapshot(), 'controllerState': self._controller.read_state(), 'updatedAt': round(time.time(), 3)}
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
            status = str(handle.get('status', '')).strip()
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
        commands = self._executor.build_command_stream(stages, task_id)
        self._active_runtime_request = {'requestId': request_id, 'taskId': task_id, 'correlationId': correlation_id, 'taskRunId': task_run_id}
        self._last_execution = {'status': 'validated', 'taskId': task_id, 'message': validation.message, 'stageCount': validation.stage_count, 'commandCount': len(commands), 'planId': commands[0].get('plan_id') if commands else ''}
        for command in commands:
            self._executor.dispatch_stage(command, started_monotonic=time.monotonic())
            self._controller.send_command(command)
            if bool(self.get_parameter('forward_hardware_commands').value):
                self._hardware_cmd_pub.publish(String(data=json.dumps(command, ensure_ascii=False)))
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
        if bool(self.get_parameter('forward_hardware_commands').value):
            self._last_execution['status'] = 'forwarded'

    def _on_hardware_feedback(self, msg: String) -> None:
        feedback = self._parse_json(msg.data)
        if not feedback:
            return
        controller_feedback = self._controller.accept_feedback(feedback)
        result = self._executor.accept_feedback(feedback)
        snapshot = self._executor.snapshot()
        self._last_execution = {'status': result.status, 'taskId': snapshot.get('taskId', ''), 'message': result.message, 'commandId': result.command_id, 'stageName': result.stage_name, 'feedbackSource': result.feedback_source, 'controllerFeedback': controller_feedback}
        if not self._active_runtime_request:
            return
        handles = list((snapshot.get('handles') or {}).values())
        handle_statuses = {str(item.get('resultStatus', '')) for item in handles}
        if result.status in {'failed', 'timeout', 'canceled'}:
            self._publish_execution_status(build_execution_status(
                request_id=str(self._active_runtime_request.get('requestId', '')),
                task_id=str(self._active_runtime_request.get('taskId', '')),
                status=result.status,
                message=result.message,
                stage_name=result.stage_name,
                command_id=result.command_id,
                correlation_id=str(self._active_runtime_request.get('correlationId', '')),
                task_run_id=str(self._active_runtime_request.get('taskRunId', '')),
            ))
            self._active_runtime_request = {}
            return
        if handles and handle_statuses == {'done'}:
            self._publish_execution_status(build_execution_status(
                request_id=str(self._active_runtime_request.get('requestId', '')),
                task_id=str(self._active_runtime_request.get('taskId', '')),
                status='done',
                message='execution finished',
                stage_name=result.stage_name,
                command_id=result.command_id,
                correlation_id=str(self._active_runtime_request.get('correlationId', '')),
                task_run_id=str(self._active_runtime_request.get('taskRunId', '')),
            ))
            self._active_runtime_request = {}

    def _on_hardware_state(self, msg: String) -> None:
        state = self._parse_json(msg.data)
        if state:
            self._last_execution['hardwareState'] = state

    def _on_system_fault(self, msg: String) -> None:
        fault = self._parse_json(msg.data)
        if fault:
            self._last_execution = {'status': 'failed', 'message': str(fault.get('message', 'system fault')), 'fault': fault}

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
        command = {'kind': 'HOME', 'task_id': 'executor-home-sequence', 'timeout_sec': 1.0, 'command_id': 'executor-home-sequence:1:go_home', 'plan_id': 'home-sequence', 'stage': 'go_home'}
        self._executor.dispatch_stage(command, started_monotonic=time.monotonic())
        self._controller.send_command(command)
        if bool(self.get_parameter('forward_hardware_commands').value):
            self._hardware_cmd_pub.publish(String(data=json.dumps(command, ensure_ascii=False)))
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
