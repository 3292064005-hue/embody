from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from math import isfinite
from typing import Any, Iterable

from arm_backend_common.stage_plan import StagePlan


@dataclass
class ExecutionResult:
    """Validation or execution outcome returned to callers."""

    accepted: bool
    stage_count: int
    message: str
    status: str = 'validated'
    stage_name: str = ''
    command_id: str = ''
    feedback_source: str = ''


@dataclass
class ExecutionHandle:
    """Tracked execution handle for a dispatched stage."""

    stage_name: str
    command_id: str
    timeout_sec: float
    started_monotonic: float = 0.0
    result_status: str = 'queued'
    feedback_source: str = ''
    message: str = ''


@dataclass
class ExecutionState:
    """Snapshot of executor runtime state."""

    task_id: str
    plan_id: str
    handles: dict[str, ExecutionHandle] = field(default_factory=dict)
    status: str = 'idle'


class MotionExecutor:
    """Motion executor that validates plans and correlates runtime feedback."""

    STAGE_ORDER = ('move_to_pregrasp', 'descend', 'close_gripper', 'lift', 'move_to_place', 'open_gripper', 'retreat', 'go_home')
    _POSE_STAGES = {'move_to_pregrasp', 'descend', 'lift', 'move_to_place', 'retreat'}

    def __init__(self) -> None:
        """Initialize executor runtime state.

        Args:
            None.

        Returns:
            None.

        Raises:
            Does not raise.
        """
        self._state = ExecutionState(task_id='', plan_id='')

    def _validate_stage_payload(self, stage: StagePlan) -> None:
        """Validate a stage payload before execution.

        Args:
            stage: Stage to validate.

        Returns:
            None.

        Raises:
            ValueError: If required fields are missing or invalid.
        """
        payload = dict(stage.payload)
        if stage.name in self._POSE_STAGES:
            required = {'x', 'y', 'z', 'yaw'}
            missing = required.difference(payload)
            if missing:
                raise ValueError(f'{stage.name} missing payload fields: {sorted(missing)}')
            for key in required:
                if not isfinite(float(payload[key])):
                    raise ValueError(f'{stage.name} payload field {key} must be finite')
        elif stage.name == 'go_home':
            if payload.get('named_pose') != 'home':
                raise ValueError('go_home stage must target named pose home')
        elif stage.kind == 'gripper':
            if 'open' not in payload:
                raise ValueError(f'{stage.name} missing gripper open flag')
        timeout = float(payload.get('timeoutSec', 1.0))
        if timeout <= 0.0:
            raise ValueError(f'{stage.name} timeout must be positive')

    def validate(self, plan: Iterable[StagePlan]) -> ExecutionResult:
        """Validate a full execution plan.

        Args:
            plan: Stage plan iterable.

        Returns:
            ExecutionResult: Validation outcome.

        Raises:
            Does not raise. Validation failures are returned in the result object.
        """
        stages = list(plan)
        if not stages:
            return ExecutionResult(False, 0, 'empty plan', status='rejected')
        names = [item.name for item in stages]
        if names != list(self.STAGE_ORDER):
            return ExecutionResult(False, len(stages), 'plan stage order invalid', status='rejected')
        try:
            for stage in stages:
                self._validate_stage_payload(stage)
        except ValueError as exc:
            return ExecutionResult(False, len(stages), str(exc), status='rejected')
        return ExecutionResult(True, len(stages), 'plan validated', status='validated')

    def build_command_stream(self, plan: Iterable[StagePlan], task_id: str) -> list[dict[str, Any]]:
        """Build serialized controller commands for a stage plan.

        Args:
            plan: Stage plan iterable.
            task_id: Task identifier.

        Returns:
            list[dict[str, Any]]: Serialized command stream.

        Raises:
            Does not raise.
        """
        commands: list[dict[str, Any]] = []
        plan_id = f'plan-{uuid.uuid4().hex[:10]}'
        stage_count = 0
        for index, stage in enumerate(plan, start=1):
            stage_count += 1
            timeout_sec = float(stage.payload.get('timeoutSec', 1.0))
            command_id = f'{task_id}:{index}:{stage.name}'
            base = {
                'command_id': command_id,
                'plan_id': plan_id,
                'task_id': task_id,
                'stage': stage.name,
                'timeout_sec': timeout_sec,
                'sequence_hint': index,
                'stage_count': len(self.STAGE_ORDER),
            }
            if stage.kind == 'gripper':
                commands.append({**base, 'kind': 'OPEN_GRIPPER' if stage.payload.get('open', False) else 'CLOSE_GRIPPER'})
            elif stage.name == 'go_home':
                commands.append({**base, 'kind': 'HOME'})
            else:
                pose = {key: value for key, value in stage.payload.items() if key != 'timeoutSec'}
                commands.append({**base, 'kind': 'EXEC_STAGE', 'pose': pose})
        if commands:
            commands[0]['stage_count'] = stage_count
        return commands

    def dispatch_stage(self, command: dict[str, Any], *, started_monotonic: float = 0.0) -> ExecutionHandle:
        """Register a dispatched command as the active execution state.

        Args:
            command: Serialized controller command.
            started_monotonic: Dispatch monotonic timestamp.

        Returns:
            ExecutionHandle: Registered execution handle.

        Raises:
            ValueError: If the command lacks required execution metadata.
        """
        command_id = str(command.get('command_id', '')).strip()
        stage_name = str(command.get('stage', '')).strip()
        task_id = str(command.get('task_id', '')).strip()
        plan_id = str(command.get('plan_id', '')).strip()
        timeout_sec = float(command.get('timeout_sec', 0.0))
        if not command_id or not stage_name or not task_id or not plan_id:
            raise ValueError('command must include command_id, stage, task_id, and plan_id')
        if timeout_sec <= 0.0:
            raise ValueError('command timeout_sec must be positive')
        if self._state.task_id != task_id or self._state.plan_id != plan_id:
            self._state = ExecutionState(task_id=task_id, plan_id=plan_id, status='dispatching')
        handle = ExecutionHandle(stage_name=stage_name, command_id=command_id, timeout_sec=timeout_sec, started_monotonic=started_monotonic, result_status='dispatching')
        self._state.handles[command_id] = handle
        self._state.status = 'dispatching'
        return handle

    def accept_feedback(self, feedback: dict[str, Any]) -> ExecutionResult:
        """Accept runtime feedback for a dispatched command.

        Args:
            feedback: Controller or hardware feedback payload.

        Returns:
            ExecutionResult: Updated execution outcome.

        Raises:
            ValueError: If feedback lacks a command identifier.
        """
        command_id = str(feedback.get('command_id', '')).strip()
        if not command_id:
            raise ValueError('feedback must include command_id')
        handle = self._state.handles.get(command_id)
        if handle is None:
            return ExecutionResult(False, len(self._state.handles), 'unknown command feedback', status='failed', command_id=command_id)
        status = str(feedback.get('status', 'waiting_feedback')).strip() or 'waiting_feedback'
        handle.result_status = status
        handle.feedback_source = str(feedback.get('source', 'hardware')).strip() or 'hardware'
        handle.message = str(feedback.get('message', ''))
        self._state.status = status
        return ExecutionResult(status not in {'failed', 'timeout'}, len(self._state.handles), handle.message or status, status=status, stage_name=handle.stage_name, command_id=command_id, feedback_source=handle.feedback_source)

    def mark_timeout(self, command_id: str, *, source: str = 'executor') -> ExecutionResult:
        """Mark an execution handle as timed out.

        Args:
            command_id: Timed out command identifier.
            source: Reporting component.

        Returns:
            ExecutionResult: Timeout outcome.

        Raises:
            ValueError: If ``command_id`` is empty.
        """
        if not str(command_id).strip():
            raise ValueError('command_id must be non-empty')
        handle = self._state.handles.get(command_id)
        if handle is None:
            return ExecutionResult(False, len(self._state.handles), 'unknown command timeout', status='timeout', command_id=command_id, feedback_source=source)
        handle.result_status = 'timeout'
        handle.feedback_source = source
        handle.message = 'execution timed out'
        self._state.status = 'timeout'
        return ExecutionResult(False, len(self._state.handles), handle.message, status='timeout', stage_name=handle.stage_name, command_id=command_id, feedback_source=source)

    def cancel(self, command_id: str, *, source: str = 'executor') -> ExecutionResult:
        """Cancel a tracked execution handle.

        Args:
            command_id: Command identifier.
            source: Reporting component.

        Returns:
            ExecutionResult: Cancel outcome.

        Raises:
            ValueError: If ``command_id`` is empty.
        """
        if not str(command_id).strip():
            raise ValueError('command_id must be non-empty')
        handle = self._state.handles.get(command_id)
        if handle is None:
            return ExecutionResult(False, len(self._state.handles), 'unknown command cancel', status='canceled', command_id=command_id, feedback_source=source)
        handle.result_status = 'canceled'
        handle.feedback_source = source
        handle.message = 'execution canceled'
        self._state.status = 'canceled'
        return ExecutionResult(False, len(self._state.handles), handle.message, status='canceled', stage_name=handle.stage_name, command_id=command_id, feedback_source=source)

    def snapshot(self) -> dict[str, Any]:
        """Return the current execution-state snapshot.

        Args:
            None.

        Returns:
            dict[str, Any]: Serializable execution-state snapshot.

        Raises:
            Does not raise.
        """
        return {
            'taskId': self._state.task_id,
            'planId': self._state.plan_id,
            'status': self._state.status,
            'handles': {
                command_id: {
                    'stageName': handle.stage_name,
                    'timeoutSec': handle.timeout_sec,
                    'resultStatus': handle.result_status,
                    'feedbackSource': handle.feedback_source,
                    'message': handle.message,
                }
                for command_id, handle in self._state.handles.items()
            },
        }
