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
from arm_task_orchestrator.task_plugins import resolve_task_runtime_plugin
from arm_perception import VisionTargetTracker
from arm_bt_runtime import BehaviorTreeRuntime, TickContext


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
    readiness_snapshot: dict[str, Any] = field(default_factory=dict)
    readiness_received_monotonic: float = 0.0
    bt_trace: list[str] = field(default_factory=list)
    bt_status_by_node: dict[str, str] = field(default_factory=dict)
    bt_node_tick_durations_ms: dict[str, float] = field(default_factory=dict)
    bt_snapshots: list[dict[str, Any]] = field(default_factory=list)
    bt_last_status: str = 'IDLE'
    bt_tick_count: int = 0

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
        self.bt_trace = []
        self.bt_status_by_node = {}
        self.bt_node_tick_durations_ms = {}
        self.bt_snapshots = []
        self.bt_last_status = 'IDLE'
        self.bt_tick_count = 0


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
        behavior_tree: BehaviorTreeRuntime | None = None,
    ) -> None:
        self._state_machine = state_machine
        self._application = application
        self._execution = execution_adapter
        self._fault_manager = fault_manager
        self._tracker = tracker
        self._state = state
        self._hooks = hooks
        self._behavior_tree = behavior_tree
        self._bt_context = TickContext(values={'checks': {}, 'event_statuses': {}, 'events': []}) if behavior_tree is not None else None

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

    def _active_plugin(self):
        current = self._state.current
        if current is None:
            return resolve_task_runtime_plugin('')
        return resolve_task_runtime_plugin(current.task_type, metadata=getattr(current, 'metadata', {}))

    def _reset_behavior_tree_runtime(self) -> None:
        if self._bt_context is None:
            self._state.bt_trace = []
            self._state.bt_status_by_node = {}
            self._state.bt_node_tick_durations_ms = {}
            self._state.bt_snapshots = []
            self._state.bt_last_status = 'IDLE'
            self._state.bt_tick_count = 0
            return
        self._bt_context = TickContext(values={'checks': {}, 'event_statuses': {}, 'events': []})
        self._state.bt_trace = []
        self._state.bt_status_by_node = {}
        self._state.bt_node_tick_durations_ms = {}
        self._state.bt_snapshots = []
        self._state.bt_last_status = 'IDLE'
        self._state.bt_tick_count = 0

    def _behavior_tree_policy(self) -> dict[str, Any]:
        current = self._state.current
        if current is None:
            return {}
        metadata = current.metadata if isinstance(current.metadata, dict) else {}
        graph = metadata.get('taskGraph') if isinstance(metadata.get('taskGraph'), dict) else {}
        recovery = graph.get('recoveryPolicy') if isinstance(graph.get('recoveryPolicy'), dict) else graph.get('recovery') if isinstance(graph.get('recovery'), dict) else {}
        max_automatic_retry = int(recovery.get('maxAutomaticRetry', current.max_retry) or current.max_retry)
        max_retries = int(recovery.get('maxRetries', current.max_retry) or current.max_retry)
        retry_mode = str(recovery.get('mode', 'retry_or_fail_closed') or 'retry_or_fail_closed')
        current_retry = max(0, int(current.current_retry))
        return {
            'mode': retry_mode,
            'autoRetryEnabled': bool(current.auto_retry),
            'maxAutomaticRetry': max(0, max_automatic_retry),
            'maxRetries': max(0, max_retries),
            'currentRetry': current_retry,
            'automaticRetryAllowed': bool(current.auto_retry) and current_retry <= max_automatic_retry and current_retry < max_retries,
            'manualRecoveryPreferred': retry_mode in {'manual_recovery', 'recovery_only'},
        }

    def _behavior_tree_event_statuses(self) -> dict[str, str]:
        current = self._state.current
        if current is None:
            return {}
        target_locked = bool(current.selected_target or current.target_id or self._state_machine.mode in {SystemMode.PLAN, SystemMode.EXECUTE, SystemMode.VERIFY})
        plan_ready = bool(self._state.pending_plan_request_id or self._state.plan or self._state.last_plan_result or self._state_machine.mode in {SystemMode.PLAN, SystemMode.EXECUTE, SystemMode.VERIFY})
        execution_ready = bool(self._state.pending_execution_request_id or self._state.last_execution_status or self._state_machine.mode in {SystemMode.EXECUTE, SystemMode.VERIFY})
        verification_ready = bool(self._state_machine.mode == SystemMode.VERIFY or current.stage == 'verification')
        retry_requested = bool(self._state_machine.mode == SystemMode.PERCEPTION and int(getattr(current, 'current_retry', 0) or 0) > 0)
        recovery_requested = bool(self._state_machine.mode in {SystemMode.SAFE_STOP, SystemMode.FAULT})
        return {
            'perception_requested': 'SUCCESS' if target_locked else 'RUNNING',
            'plan_requested': 'SUCCESS' if plan_ready else 'RUNNING',
            'execution_requested': 'SUCCESS' if execution_ready else 'RUNNING',
            'verification_completed': 'SUCCESS' if verification_ready else 'RUNNING',
            'retry_requested': 'SUCCESS' if retry_requested else 'RUNNING',
            'recovery_requested': 'SUCCESS' if recovery_requested else 'RUNNING',
        }

    def _tick_behavior_tree(self, *, note: str) -> None:
        if self._behavior_tree is None or self._bt_context is None:
            self._reset_behavior_tree_runtime()
            return
        current = self._state.current
        if current is None:
            self._reset_behavior_tree_runtime()
            return
        values = self._bt_context.values
        policy = self._behavior_tree_policy()
        current_retry = int(policy.get('currentRetry', 0) or 0)
        max_automatic_retry = int(policy.get('maxAutomaticRetry', current.max_retry) or current.max_retry)
        max_retries = int(policy.get('maxRetries', current.max_retry) or current.max_retry)
        values['checks'] = {
            'motion_planner': self._state_machine.mode in {SystemMode.PERCEPTION, SystemMode.PLAN, SystemMode.EXECUTE, SystemMode.VERIFY},
            'auto_retry_enabled': bool(policy.get('autoRetryEnabled', False)),
            'retry_budget_available': current_retry < max_retries,
            'automatic_retry_budget_available': bool(policy.get('automaticRetryAllowed', False)),
            'retry_pending': self._state_machine.mode == SystemMode.PERCEPTION and current_retry > 0,
            'recovery_pending': self._state_machine.mode in {SystemMode.SAFE_STOP, SystemMode.FAULT},
            'manual_recovery_preferred': bool(policy.get('manualRecoveryPreferred', False)),
            'plan_dispatch_ready': self._state_machine.mode in {SystemMode.PERCEPTION, SystemMode.PLAN, SystemMode.EXECUTE, SystemMode.VERIFY},
            'execution_dispatch_ready': self._state_machine.mode in {SystemMode.PLAN, SystemMode.EXECUTE, SystemMode.VERIFY},
            'verification_dispatch_ready': self._state_machine.mode in {SystemMode.EXECUTE, SystemMode.VERIFY},
        }
        values['event_statuses'] = self._behavior_tree_event_statuses()
        values['runtime'] = {
            'mode': self._state_machine.mode.value if hasattr(self._state_machine.mode, 'value') else str(self._state_machine.mode),
            'phase': self._state_machine.phase,
            'taskId': current.task_id,
            'note': note,
            'policy': policy,
        }
        status = self._behavior_tree.tick(self._bt_context)
        self._state.bt_trace = list(self._bt_context.trace[-64:])
        self._state.bt_status_by_node = dict(self._bt_context.status_by_node)
        self._state.bt_node_tick_durations_ms = dict(self._bt_context.node_tick_durations_ms)
        self._state.bt_snapshots = list(self._bt_context.snapshots[-8:])
        self._state.bt_last_status = status.value
        self._state.bt_tick_count = self._bt_context.tick_count
        if isinstance(current.metadata, dict):
            current.metadata['behaviorTree'] = {
                'status': self._state.bt_last_status,
                'tickCount': self._state.bt_tick_count,
                'statusByNode': dict(self._state.bt_status_by_node),
                'trace': list(self._state.bt_trace[-12:]),
                'policy': dict(policy),
            }

    def _graph_spec(self) -> dict[str, Any]:
        current = self._state.current
        if current is None or not isinstance(getattr(current, 'metadata', None), dict):
            return {}
        graph = current.metadata.get('taskGraph')
        return dict(graph) if isinstance(graph, dict) else {}

    def _set_graph_node(self, *, node_id: str | None = None, kind: str | None = None, default_stage: str = '') -> str:
        current = self._state.current
        if current is None:
            return default_stage
        metadata = current.metadata if isinstance(current.metadata, dict) else None
        graph = self._graph_spec()
        stage = str(default_stage or '')
        resolved_node = str(node_id or kind or '')
        nodes = graph.get('nodes', []) if isinstance(graph.get('nodes'), list) else []
        for item in nodes:
            if not isinstance(item, dict):
                continue
            if node_id and str(item.get('id', '')) == str(node_id):
                stage = str(item.get('stage', stage) or stage)
                resolved_node = str(item.get('id', resolved_node) or resolved_node)
                break
            if kind and str(item.get('kind', '')) == str(kind):
                stage = str(item.get('stage', stage) or stage)
                resolved_node = str(item.get('id', resolved_node) or resolved_node)
                break
        current.stage = stage
        if metadata is not None:
            metadata['activeGraphNode'] = resolved_node
            metadata['activeGraphStage'] = stage
        if stage and (not current.stage_history or current.stage_history[-1] != stage):
            current.stage_history.append(stage)
        return stage

    def update_target(self, target: TargetSnapshot) -> None:
        self._state.latest_target = target
        self._tracker.upsert(target)

    def update_feedback(self, feedback: dict[str, Any]) -> None:
        self._state.last_feedback = dict(feedback)

    def update_plan_result(self, payload: dict[str, Any]) -> None:
        self._state.last_plan_result = dict(payload)

    def update_execution_status(self, payload: dict[str, Any]) -> None:
        self._state.last_execution_status = dict(payload)

    def update_readiness_snapshot(self, payload: dict[str, Any]) -> None:
        """Store the latest authoritative readiness snapshot for task admission.

        Args:
            payload: Public readiness-state payload published by the readiness manager.

        Returns:
            None.

        Raises:
            Does not raise. Malformed inputs degrade to an empty fail-closed snapshot.
        """
        self._state.readiness_snapshot = dict(payload) if isinstance(payload, dict) else {}
        self._state.readiness_received_monotonic = time.monotonic() if self._state.readiness_snapshot else 0.0

    def update_hardware(self, hardware: HardwareSnapshot) -> None:
        self._state.hardware = hardware

    def update_calibration(self, calibration: CalibrationProfile) -> None:
        self._state.calibration = calibration

    def clear_for_fault_reset(self) -> None:
        self._state.queue.clear()
        self._state.clear_active_path()
        self._reset_behavior_tree_runtime()

    def _readiness_snapshot_age_sec(self, *, now: float | None = None) -> float:
        """Return the age of the last authoritative readiness snapshot in seconds."""
        received = float(getattr(self._state, 'readiness_received_monotonic', 0.0) or 0.0)
        if received <= 0.0:
            return float('inf')
        clock_now = time.monotonic() if now is None else float(now)
        return max(0.0, clock_now - received)

    def command_policy_decision(self, command_name: str, *, hardware_fresh_sec: float, fallback_reason: str | None = None) -> OrchestratorDecision:
        """Evaluate one readiness-owned command policy with fail-closed freshness handling.

        Args:
            command_name: Public command-policy key.
            hardware_fresh_sec: Maximum tolerated age of the last readiness snapshot.
            fallback_reason: Optional fail-closed reason when the snapshot or policy is missing.

        Returns:
            OrchestratorDecision: Allowed/blocked decision and authoritative reason.

        Raises:
            Does not raise. Missing or stale readiness snapshots are converted into deterministic rejections.

        Boundary behavior:
            The method never widens admission from a stale cached allow decision. Snapshot freshness is evaluated
            before any per-command policy is trusted.
        """
        fail_closed_reason = str(fallback_reason or f'{command_name} requires authoritative readiness snapshot')
        readiness = self._state.readiness_snapshot if isinstance(self._state.readiness_snapshot, dict) else {}
        if not readiness:
            return OrchestratorDecision(stage='blocked', accepted=False, message=fail_closed_reason, fault=FaultCode.UNKNOWN)
        if hardware_fresh_sec > 0.0 and self._readiness_snapshot_age_sec() > float(hardware_fresh_sec):
            return OrchestratorDecision(stage='blocked', accepted=False, message='authoritative readiness snapshot stale', fault=FaultCode.UNKNOWN)
        policies = readiness.get('commandPolicies', {}) if isinstance(readiness.get('commandPolicies', {}), dict) else {}
        policy = policies.get(command_name)
        if isinstance(policy, dict):
            allowed = bool(policy.get('allowed', False))
            reason = str(policy.get('reason', fail_closed_reason) or fail_closed_reason)
            return OrchestratorDecision(stage='ready' if allowed else 'blocked', accepted=allowed, message=reason, fault=FaultCode.NONE if allowed else FaultCode.UNKNOWN)
        return OrchestratorDecision(stage='blocked', accepted=False, message=fail_closed_reason, fault=FaultCode.UNKNOWN)

    def admission_decision(self, queued: TaskRequest, *, hardware_fresh_sec: float) -> OrchestratorDecision:
        """Evaluate whether one task request may enter the runtime queue.

        Args:
            queued: Candidate task request.
            hardware_fresh_sec: Maximum tolerated age of the authoritative readiness snapshot.

        Returns:
            OrchestratorDecision: Acceptance decision with an authoritative deny reason.

        Raises:
            Does not raise. Missing readiness snapshots degrade to fail-closed rejection.

        Boundary behavior:
            The decision prefers the readiness manager's public ``startTask`` policy. Missing or stale snapshots reject
            the request instead of widening admission to a cached or hardware-only check.
        """
        policy = self.command_policy_decision(
            'startTask',
            hardware_fresh_sec=hardware_fresh_sec,
            fallback_reason='task execution requires authoritative readiness snapshot',
        )
        return self._application.accept_request(queued, policy.accepted, policy.message)

    def enqueue_task_request(self, queued: TaskRequest, *, hardware_fresh_sec: float) -> OrchestratorDecision:
        decision = self.admission_decision(queued, hardware_fresh_sec=hardware_fresh_sec)
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
        self._reset_behavior_tree_runtime()
        return transition.reason

    def elapsed_for_task(self, task_id: str) -> float:
        if self._state.current is not None and self._state.current.task_id == task_id:
            return self._state.current.elapsed()
        return float(self._state.task_outcomes.get(task_id, {}).get('elapsed', 0.0))

    def continue_with_next_target(
        self,
        message: str,
        *,
        perception_blocked_after_sec: float,
        reason_suffix: str,
        mark_selected_completed: bool,
    ) -> bool:
        """Route the active task back to perception with the next target.

        Args:
            message: Runtime or verification message that triggered continuation.
            perception_blocked_after_sec: Fail-closed perception wait budget for the next target.
            reason_suffix: Human-readable suffix appended to the runtime message.
            mark_selected_completed: Whether the currently selected target should be
                excluded from future selection before returning to perception.

        Returns:
            bool: ``True`` when the runtime consumed the transition and remained
            active; ``False`` when no current task exists.

        Boundary behavior:
            The helper clears plan / execution in-flight state, resets the active
            target binding and returns the state machine to ``PERCEPTION`` without
            silently completing the task.
        """
        current = self._state.current
        if current is None:
            return False
        selected_target_key = ''
        if current.selected_target is not None:
            selected_target_key = current.selected_target.key()
        elif isinstance(current.metadata, dict):
            selected_target_key = str(current.metadata.get('_lastSelectedTargetKey', '') or '')
        if mark_selected_completed and selected_target_key:
            current.completed_target_ids.add(selected_target_key)
        current.selected_target = None
        current.target_id = None
        current.active_place_pose = {}
        current.reserved_target_key = None
        current.plan_deadline = 0.0
        current.execute_deadline = 0.0
        current.verify_deadline = time.monotonic() + self._state.task_profile.verify_timeout_sec
        current.perception_deadline = time.monotonic() + max(perception_blocked_after_sec, 0.1)
        current.last_message = f"{message}; {reason_suffix}" if reason_suffix else str(message)
        self._state.plan = []
        self._state.pending_plan_request_id = ''
        self._state.pending_execution_request_id = ''
        self._state.last_plan_result = {}
        self._state.last_execution_status = {}
        self._set_graph_node(kind='perception', default_stage='perception')
        transition = self._state_machine.retry_to_perception(current.last_message)
        self._hooks.emit_event(
            'INFO',
            'task_orchestrator',
            'TASK_CONTINUED',
            current.task_id,
            0,
            transition.reason,
            stage='perception',
        )
        self._tick_behavior_tree(note='continue_next_target')
        return True

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
            episode_id=getattr(self._state.current, 'episode_id', ''),
        )
        self._set_graph_node(kind='planning', default_stage='planning')
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
            episode_id=getattr(self._state.current, 'episode_id', ''),
        )
        self._set_graph_node(kind='execution', default_stage='execution')
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

    def tick(self, *, hardware_fresh_sec: float, command_timeout_sec: float, perception_blocked_after_sec: float = 2.5) -> None:
        self._tracker.prune()
        if self._state.current is None:
            if self._state.queue:
                request = self._state.queue.popleft()
                self._state.current = self._application.begin_task(request)
                plugin = self._active_plugin()
                self._state.current.metadata.setdefault('pluginKey', plugin.key)
                now = time.monotonic()
                self._state.current.verify_deadline = now + self._state.task_profile.verify_timeout_sec
                self._state.current.perception_deadline = now + max(perception_blocked_after_sec, 0.1)
                transition = self._state_machine.start_task(f'Task {request.task_id} started')
                self._hooks.emit_event('INFO', 'task_orchestrator', 'TASK_STARTED', request.task_id, 0, transition.reason, stage='perception')
                current = dict(self._state.task_outcomes.get(request.task_id, {}))
                current.update({'state': 'running', 'message': transition.reason, 'terminal': False})
                self._state.task_outcomes[request.task_id] = current
                self._reset_behavior_tree_runtime()
                self._tick_behavior_tree(note='task_started')
            return

        if self._state_machine.mode == SystemMode.PERCEPTION:
            plugin = self._active_plugin()
            target = plugin.target_selector.select_target(self)
            self._tick_behavior_tree(note='perception')
            if target is None:
                now = time.monotonic()
                if self._state.current.perception_deadline <= 0.0:
                    self._state.current.perception_deadline = now + max(perception_blocked_after_sec, 0.1)
                if now > self._state.current.perception_deadline:
                    transition = self._state_machine.perception_blocked('No authoritative target available')
                    self._state.current.last_message = transition.reason
                    self._hooks.emit_event('WARN', 'task_orchestrator', 'BLOCKED_BY_PERCEPTION', self._state.current.task_id, int(FaultCode.TARGET_NOT_FOUND), transition.reason, stage='perception', error_code='blocked_by_perception', operator_actionable=True)
                elif self._state_machine.phase != 'WAIT_TARGET':
                    transition = self._state_machine.perception_waiting('Waiting for authoritative target')
                    self._state.current.last_message = transition.reason
                return
            self._state.current.perception_deadline = 0.0
            self._hooks.publish_selected_target(target.to_dict())
            if not self._state.pending_plan_request_id:
                self._application.bind_target(self._state.current, target, self._state.calibration)
                self._state_machine.perception_ok('Valid target acquired')
                self._publish_plan_request(target=target, command_timeout_sec=command_timeout_sec)
                self._tick_behavior_tree(note='plan_requested')
            return

        if self._state_machine.mode == SystemMode.PLAN:
            self._tick_behavior_tree(note='planning')
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
            plugin = self._active_plugin()
            if plugin.stage_policy.on_plan_accepted(self, result, contract=plugin.stage_contract('planning')):
                return
            transition = self._state_machine.plan_ok('Plan accepted by motion planner')
            self._hooks.emit_event('INFO', 'task_orchestrator', 'PLAN_READY', self._state.current.task_id, 0, transition.reason, stage='plan')
            self._publish_execution_request(command_timeout_sec=command_timeout_sec)
            self._tick_behavior_tree(note='execution_requested')
            return

        if self._state_machine.mode == SystemMode.EXECUTE:
            self._tick_behavior_tree(note='execution')
            if self._state.current.execute_deadline and time.monotonic() > self._state.current.execute_deadline:
                self.enter_fault(FaultCode.EXECUTE_TIMEOUT, detail='execution status timeout')
                return
            status_payload = self._consume_matching_execution_status()
            if status_payload is None:
                return
            status = str(status_payload.get('status', '')).strip().lower()
            if status in {'done', 'succeeded'}:
                plugin = self._active_plugin()
                if plugin.stage_policy.on_execution_success(self, status_payload, contract=plugin.stage_contract('execution')):
                    return
                transition = self._state_machine.execute_ok('Execution finished')
                self._set_graph_node(kind='verification', default_stage='verification')
                self._state.current.verify_deadline = time.monotonic() + self._state.task_profile.verify_timeout_sec
                self._hooks.emit_event('INFO', 'task_orchestrator', 'EXECUTION_FINISHED', self._state.current.task_id, 0, transition.reason, stage='verify')
                self._tick_behavior_tree(note='execution_finished')
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
            self._set_graph_node(kind='verification', default_stage='verification')
            self._tick_behavior_tree(note='verification')
            if self._state.current.selected_target is not None and isinstance(self._state.current.metadata, dict):
                self._state.current.metadata['_lastSelectedTargetKey'] = self._state.current.selected_target.key()
            result = self._application.verify_outcome(
                self._state.current,
                self._state.hardware,
                self._tracker.select(self._state.current.target_selector, exclude_keys=self._state.current.completed_target_ids),
                time.monotonic(),
            )
            if not result.finished:
                return
            if result.success:
                plugin = self._active_plugin()
                if plugin.stage_policy.on_verify_success(
                    self,
                    result.message,
                    perception_blocked_after_sec=perception_blocked_after_sec,
                    contract=plugin.stage_contract('verification'),
                ):
                    return
                self._application.complete(self._state.current, result.message)
                self._set_graph_node(kind='terminal', default_stage='complete')
                transition = self._state_machine.verify_ok(result.message)
                self._hooks.emit_event('INFO', 'task_orchestrator', 'TASK_COMPLETED', self._state.current.task_id, 0, transition.reason, stage='finish')
                self.mark_task_terminal(self._state.current.task_id, state='succeeded', result_code=0, message=transition.reason, elapsed=self._state.current.elapsed())
                self._state.clear_active_path()
                self._reset_behavior_tree_runtime()
                return
            retryable = result.fault in self._fault_manager.RETRYABLE
            self._hooks.emit_event('WARN', 'task_orchestrator', 'TASK_RETRY' if retryable else 'TASK_FAILED', getattr(self._state.current, 'task_id', ''), int(result.fault), result.message, stage='verify', error_code=str(result.fault.name).lower(), operator_actionable=not retryable)
            if retryable:
                plugin = self._active_plugin()
                if plugin.recovery_policy.on_retryable_fault(
                    self,
                    message=result.message,
                    perception_blocked_after_sec=perception_blocked_after_sec,
                    contract=plugin.stage_contract('verification'),
                ):
                    return
                self._state.plan = []
                self._state.pending_plan_request_id = ''
                self._state.pending_execution_request_id = ''
                self._state.last_plan_result = {}
                self._state.last_execution_status = {}
                self._state.current.perception_deadline = time.monotonic() + max(perception_blocked_after_sec, 0.1)
                self._set_graph_node(kind='perception', default_stage='perception')
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
        self._set_graph_node(default_stage='fault')
        task_id = getattr(self._state.current, 'task_id', '')
        transition = self._state_machine.fault(code, message)
        self._hooks.emit_event('ERROR', 'task_orchestrator', 'FAULT', task_id, int(code), transition.reason, stage='fault', error_code=str(code.name).lower(), operator_actionable=True)
        self._hooks.publish_fault(code, task_id, message)
        if task_id:
            self.mark_task_terminal(task_id, state='aborted', result_code=int(code), message=message, elapsed=self.elapsed_for_task(task_id))
        self._state.clear_active_path()
        self._reset_behavior_tree_runtime()
