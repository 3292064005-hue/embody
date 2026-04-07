from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Callable

from arm_backend_common.data_models import CalibrationProfile, HardwareSnapshot, TargetSnapshot, TaskContext, TaskProfile, TaskRequest
from arm_backend_common.enums import FaultCode, SystemMode
from arm_backend_common.error_codes import fault_message
from arm_common.runtime_contracts import build_execution_request, build_planning_request, stage_plan_from_dict
from arm_task_orchestrator.application_service import TaskApplicationService
from arm_task_orchestrator.execution_adapter import AwaitingCommand, ExecutionAdapter
from arm_task_orchestrator.fault_manager import FaultManager
from arm_task_orchestrator.orchestrator import OrchestratorDecision
from arm_task_orchestrator.state_machine import SystemStateMachine
from arm_perception import VisionTargetTracker


@dataclass(slots=True)
class RuntimeHooks:
    emit_event: Callable[..., None]
    send_hardware_command: Callable[[dict[str, Any]], None]
    publish_selected_target: Callable[[dict[str, Any]], None]
    publish_fault: Callable[[FaultCode, str, str], None]
    publish_planning_request: Callable[[dict[str, Any]], None]
    publish_execution_request: Callable[[dict[str, Any]], None]


@dataclass(slots=True)
class TaskRuntimeState:
    """Mutable runtime aggregate owned by the task orchestrator engine."""

    task_profile: TaskProfile
    hardware: HardwareSnapshot = field(default_factory=HardwareSnapshot)
    calibration: CalibrationProfile = field(default_factory=CalibrationProfile)
    queue: deque[TaskRequest] = field(default_factory=deque)
    current: TaskContext | None = None
    plan: list[Any] = field(default_factory=list)
    command_queue: deque[dict[str, Any]] = field(default_factory=deque)
    awaiting: dict[str, Any] | None = None
    awaiting_state: AwaitingCommand | None = None
    last_feedback: dict[str, Any] = field(default_factory=dict)
    latest_target: TargetSnapshot | None = None
    task_outcomes: dict[str, dict[str, Any]] = field(default_factory=dict)
    pending_plan_request_id: str = ''
    pending_execution_request_id: str = ''
    last_plan_result: dict[str, Any] = field(default_factory=dict)
    last_execution_status: dict[str, Any] = field(default_factory=dict)

    def clear_active_path(self) -> None:
        self.current = None
        self.plan = []
        self.command_queue.clear()
        self.awaiting = None
        self.awaiting_state = None
        self.pending_plan_request_id = ''
        self.pending_execution_request_id = ''
        self.last_plan_result = {}
        self.last_execution_status = {}


class TaskRuntimeEngine:
    """Pure runtime engine for queue progression and state transitions.

    The orchestrator now treats planning and execution as explicit split-stack
    runtime contracts rather than directly instantiating planner/executor logic
    in-process.
    """

    def __init__(
        self,
        *,
        state_machine: SystemStateMachine,
        application: TaskApplicationService,
        execution_adapter: ExecutionAdapter,
        fault_manager: FaultManager,
        tracker: VisionTargetTracker,
        state: TaskRuntimeState,
        hooks: RuntimeHooks,
    ) -> None:
        self._state_machine = state_machine
        self._application = application
        self._execution = execution_adapter
        self._fault_manager = fault_manager
        self._tracker = tracker
        self._state = state
        self._hooks = hooks

    @property
    def state(self) -> TaskRuntimeState:
        return self._state

    @property
    def tracker(self) -> VisionTargetTracker:
        return self._tracker

    def replace_tracker(self, tracker: VisionTargetTracker) -> None:
        self._tracker = tracker

    def replace_task_profile(self, task_profile: TaskProfile) -> None:
        self._state.task_profile = task_profile

    def update_target(self, target: TargetSnapshot) -> None:
        self._state.latest_target = target
        self._tracker.upsert(target)

    def update_feedback(self, feedback: dict[str, Any]) -> None:
        self._state.last_feedback = dict(feedback)

    def update_plan_result(self, payload: dict[str, Any]) -> None:
        self._state.last_plan_result = dict(payload)

    def update_execution_status(self, payload: dict[str, Any]) -> None:
        self._state.last_execution_status = dict(payload)

    def update_hardware(self, hardware: HardwareSnapshot) -> None:
        self._state.hardware = hardware

    def update_calibration(self, calibration: CalibrationProfile) -> None:
        self._state.calibration = calibration

    def clear_for_fault_reset(self) -> None:
        self._state.queue.clear()
        self._state.clear_active_path()

    def enqueue_task_request(self, queued: TaskRequest, *, hardware_fresh_sec: float) -> OrchestratorDecision:
        readiness_ok = self._state.hardware.is_ready(stale_after_sec=hardware_fresh_sec)
        decision = self._application.accept_request(queued, readiness_ok, 'ready' if readiness_ok else 'hardware not ready')
        if decision.accepted:
            self._state.queue.append(queued)
            self._state.task_outcomes[queued.task_id] = {'terminal': False, 'state': 'queued', 'message': decision.message, 'result_code': 0}
            self._hooks.emit_event('INFO', 'task_orchestrator', 'TASK_ENQUEUED', queued.task_id, 0, decision.message, stage='queue')
        else:
            self._state.task_outcomes[queued.task_id] = {'terminal': True, 'state': 'rejected', 'message': decision.message, 'result_code': int(decision.fault)}
        return decision

    def mark_task_terminal(self, task_id: str, *, state: str, result_code: int, message: str, elapsed: float | None = None) -> None:
        current = dict(self._state.task_outcomes.get(task_id, {}))
        current.update({'terminal': True, 'state': state, 'result_code': int(result_code), 'message': message})
        if elapsed is not None:
            current['elapsed'] = float(elapsed)
        self._state.task_outcomes[task_id] = current

    def cancel_task_by_id(self, task_id: str, reason: str) -> None:
        if not task_id:
            return
        for queued in list(self._state.queue):
            if queued.task_id == task_id:
                self._state.queue.remove(queued)
                self.mark_task_terminal(task_id, state='canceled', result_code=int(FaultCode.UNKNOWN), message=reason, elapsed=0.0)
                self._hooks.emit_event('WARN', 'task_orchestrator', 'TASK_CANCELED', task_id, int(FaultCode.UNKNOWN), reason, stage='queue', error_code='task_canceled', operator_actionable=True)
                return
        if self._state.current is not None and self._state.current.task_id == task_id:
            self.perform_stop(reason, canceled_task_id=task_id)

    def perform_stop(self, reason: str, canceled_task_id: str | None = None) -> str:
        self._state.queue.clear()
        active_task_id = canceled_task_id or getattr(self._state.current, 'task_id', '')
        self._hooks.send_hardware_command({'kind': 'STOP', 'task_id': active_task_id or 'system', 'timeout_sec': 0.4})
        transition = self._state_machine.safe_stop(reason)
        self._hooks.emit_event('WARN', 'task_orchestrator', 'SAFE_STOP', active_task_id, 0, transition.reason, stage='safe_stop', error_code='safe_stop', operator_actionable=True)
        if active_task_id:
            self.mark_task_terminal(active_task_id, state='canceled', result_code=int(FaultCode.UNKNOWN), message=transition.reason, elapsed=self.elapsed_for_task(active_task_id))
        self._state.clear_active_path()
        return transition.reason

    def elapsed_for_task(self, task_id: str) -> float:
        if self._state.current is not None and self._state.current.task_id == task_id:
            return self._state.current.elapsed()
        return float(self._state.task_outcomes.get(task_id, {}).get('elapsed', 0.0))

    def _publish_plan_request(self, *, target: TargetSnapshot, command_timeout_sec: float) -> None:
        if self._state.current is None:
            return
        request_id = f"plan-{self._state.current.task_id}-{int(time.monotonic() * 1000)}"
        self._state.pending_plan_request_id = request_id
        self._state.current.plan_deadline = time.monotonic() + max(command_timeout_sec, 0.1)
        payload = build_planning_request(
            request_id=request_id,
            context=self._state.current,
            target=target,
            calibration=self._state.calibration,
            correlation_id=getattr(self._state.current, 'correlation_id', ''),
            task_run_id=getattr(self._state.current, 'task_run_id', ''),
        )
        self._hooks.publish_planning_request(payload)
        self._hooks.emit_event('INFO', 'task_orchestrator', 'PLAN_REQUESTED', self._state.current.task_id, 0, 'planning request published', stage='plan')

    def _publish_execution_request(self, *, command_timeout_sec: float) -> None:
        if self._state.current is None or not self._state.plan:
            return
        request_id = f"exec-{self._state.current.task_id}-{int(time.monotonic() * 1000)}"
        self._state.pending_execution_request_id = request_id
        self._state.current.execute_deadline = time.monotonic() + max(command_timeout_sec, 0.1)
        payload = build_execution_request(
            request_id=request_id,
            task_id=self._state.current.task_id,
            plan=list(self._state.plan),
            correlation_id=getattr(self._state.current, 'correlation_id', ''),
            task_run_id=getattr(self._state.current, 'task_run_id', ''),
        )
        self._hooks.publish_execution_request(payload)
        self._hooks.emit_event('INFO', 'task_orchestrator', 'EXECUTION_REQUESTED', self._state.current.task_id, 0, 'execution request published', stage='execute')

    def _consume_matching_plan_result(self) -> dict[str, Any] | None:
        payload = dict(self._state.last_plan_result)
        if not payload:
            return None
        if str(payload.get('requestId', '')) != self._state.pending_plan_request_id:
            return None
        if self._state.current is not None and str(payload.get('taskId', '')) not in {'', self._state.current.task_id}:
            return None
        if self._state.current is not None and str(payload.get('correlationId', '') or '') not in {'', getattr(self._state.current, 'correlation_id', '')}:
            return None
        if self._state.current is not None and str(payload.get('taskRunId', '') or '') not in {'', getattr(self._state.current, 'task_run_id', '')}:
            return None
        self._state.last_plan_result = {}
        self._state.pending_plan_request_id = ''
        return payload

    def _consume_matching_execution_status(self) -> dict[str, Any] | None:
        payload = dict(self._state.last_execution_status)
        if not payload:
            return None
        if str(payload.get('requestId', '')) != self._state.pending_execution_request_id:
            return None
        if self._state.current is not None and str(payload.get('taskId', '')) not in {'', self._state.current.task_id}:
            return None
        if self._state.current is not None and str(payload.get('correlationId', '') or '') not in {'', getattr(self._state.current, 'correlation_id', '')}:
            return None
        if self._state.current is not None and str(payload.get('taskRunId', '') or '') not in {'', getattr(self._state.current, 'task_run_id', '')}:
            return None
        status = str(payload.get('status', '')).strip().lower()
        if status not in {'done', 'succeeded', 'failed', 'timeout', 'canceled', 'rejected'}:
            return None
        self._state.last_execution_status = {}
        self._state.pending_execution_request_id = ''
        return payload

    def tick(self, *, hardware_fresh_sec: float, command_timeout_sec: float) -> None:
        self._tracker.prune()
        if self._state.current is None:
            if self._state.queue:
                request = self._state.queue.popleft()
                self._state.current = self._application.begin_task(request)
                self._state.current.verify_deadline = time.monotonic() + self._state.task_profile.verify_timeout_sec
                transition = self._state_machine.start_task(f'Task {request.task_id} started')
                self._hooks.emit_event('INFO', 'task_orchestrator', 'TASK_STARTED', request.task_id, 0, transition.reason, stage='perception')
                current = dict(self._state.task_outcomes.get(request.task_id, {}))
                current.update({'state': 'running', 'message': transition.reason, 'terminal': False})
                self._state.task_outcomes[request.task_id] = current
            return

        if self._state_machine.mode == SystemMode.PERCEPTION:
            target = self._tracker.select(self._state.current.target_selector, exclude_keys=self._state.current.completed_target_ids)
            if target is None:
                return
            self._hooks.publish_selected_target(target.to_dict())
            if not self._state.pending_plan_request_id:
                self._application.bind_target(self._state.current, target, self._state.calibration)
                self._state_machine.perception_ok('Valid target acquired')
                self._publish_plan_request(target=target, command_timeout_sec=command_timeout_sec)
                return
            if self._state.current.plan_deadline and time.monotonic() > self._state.current.plan_deadline:
                self.enter_fault(FaultCode.PLAN_FAILED, detail='planning timeout')
                return
            result = self._consume_matching_plan_result()
            if result is None:
                return
            if not bool(result.get('accepted', False)):
                self.enter_fault(FaultCode.PLAN_FAILED, detail=str(result.get('message', 'planning rejected')))
                return
            self._state.plan = [stage_plan_from_dict(item) for item in list(result.get('stages') or []) if isinstance(item, dict)]
            transition = self._state_machine.plan_ok('Plan accepted by motion planner')
            self._hooks.emit_event('INFO', 'task_orchestrator', 'PLAN_READY', self._state.current.task_id, 0, transition.reason, stage='plan')
            self._publish_execution_request(command_timeout_sec=command_timeout_sec)
            return

        if self._state_machine.mode == SystemMode.EXECUTE:
            if self._state.current.execute_deadline and time.monotonic() > self._state.current.execute_deadline:
                self.enter_fault(FaultCode.EXECUTE_TIMEOUT, detail='execution status timeout')
                return
            status_payload = self._consume_matching_execution_status()
            if status_payload is None:
                return
            status = str(status_payload.get('status', '')).strip().lower()
            if status in {'done', 'succeeded'}:
                transition = self._state_machine.execute_ok('Execution finished')
                self._state.current.stage = 'verify'
                self._state.current.verify_deadline = time.monotonic() + self._state.task_profile.verify_timeout_sec
                self._hooks.emit_event('INFO', 'task_orchestrator', 'EXECUTION_FINISHED', self._state.current.task_id, 0, transition.reason, stage='verify')
                return
            if status == 'timeout':
                self.enter_fault(FaultCode.EXECUTE_TIMEOUT, detail=str(status_payload.get('message', 'execution timed out')))
                return
            if status == 'canceled':
                self.enter_fault(FaultCode.EXECUTE_CANCELED, detail=str(status_payload.get('message', 'execution canceled')))
                return
            self.enter_fault(FaultCode.UNKNOWN, detail=str(status_payload.get('message', 'execution failed')))
            return

        if self._state_machine.mode == SystemMode.VERIFY and self._state.current is not None:
            result = self._application.verify_outcome(
                self._state.current,
                self._state.hardware,
                self._tracker.select(self._state.current.target_selector, exclude_keys=self._state.current.completed_target_ids),
                time.monotonic(),
            )
            if not result.finished:
                return
            if result.success:
                self._application.complete(self._state.current, result.message)
                transition = self._state_machine.verify_ok(result.message)
                self._hooks.emit_event('INFO', 'task_orchestrator', 'TASK_COMPLETED', self._state.current.task_id, 0, transition.reason, stage='finish')
                self.mark_task_terminal(self._state.current.task_id, state='succeeded', result_code=0, message=transition.reason, elapsed=self._state.current.elapsed())
                self._state.clear_active_path()
                return
            retryable = result.fault in self._fault_manager.RETRYABLE
            self._hooks.emit_event('WARN', 'task_orchestrator', 'TASK_RETRY' if retryable else 'TASK_FAILED', getattr(self._state.current, 'task_id', ''), int(result.fault), result.message, stage='verify', error_code=str(result.fault.name).lower(), operator_actionable=not retryable)
            if retryable:
                self._state.plan = []
                self._state.pending_plan_request_id = ''
                self._state.pending_execution_request_id = ''
                self._state.last_plan_result = {}
                self._state.last_execution_status = {}
                self._state_machine.retry_to_perception(result.message)
                return
            self.enter_fault(result.fault, detail=result.message)

    def dispatch_next_command(self, *, command_timeout_sec: float) -> None:
        """Compatibility no-op retained for legacy callers.

        The split-stack executor now owns command dispatch; the orchestrator only
        publishes execution requests and observes terminal status messages.
        """
        del command_timeout_sec
        return

    def enter_fault(self, code: FaultCode, detail: str | None = None) -> None:
        message = detail or fault_message(code)
        task_id = getattr(self._state.current, 'task_id', '')
        transition = self._state_machine.fault(code, message)
        self._hooks.emit_event('ERROR', 'task_orchestrator', 'FAULT', task_id, int(code), transition.reason, stage='fault', error_code=str(code.name).lower(), operator_actionable=True)
        self._hooks.publish_fault(code, task_id, message)
        if task_id:
            self.mark_task_terminal(task_id, state='aborted', result_code=int(code), message=message, elapsed=self.elapsed_for_task(task_id))
        self._state.clear_active_path()
