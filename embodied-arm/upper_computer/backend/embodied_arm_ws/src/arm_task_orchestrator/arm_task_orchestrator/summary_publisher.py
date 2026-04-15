from __future__ import annotations

from typing import Any

from arm_backend_common.data_models import TaskContext


class SummaryPublisher:
    """Build serializable task summary and task-status payloads."""

    RUNTIME_PHASE_BY_PHASE = {
        'BOOT': 'boot',
        'IDLE': 'idle',
        'WAIT_TARGET': 'perception',
        'BLOCKED_BY_PERCEPTION': 'perception',
        'TARGET_LOCKED': 'plan',
        'EXECUTING': 'execute',
        'VERIFY_RESULT': 'verify',
        'FINISH': 'idle',
        'SAFE_STOP': 'safe_stop',
        'FAULT': 'fault',
    }
    TASK_STAGE_BY_PHASE = {
        'BOOT': 'created',
        'IDLE': 'done',
        'WAIT_TARGET': 'perception',
        'BLOCKED_BY_PERCEPTION': 'failed',
        'TARGET_LOCKED': 'plan',
        'EXECUTING': 'execute',
        'VERIFY_RESULT': 'verify',
        'FINISH': 'done',
        'SAFE_STOP': 'failed',
        'FAULT': 'failed',
    }

    def runtime_phase_from_phase(self, phase: str) -> str:
        return self.RUNTIME_PHASE_BY_PHASE.get(str(phase or 'IDLE').upper(), 'idle')

    def task_stage_from_phase(self, phase: str) -> str:
        return self.TASK_STAGE_BY_PHASE.get(str(phase or 'IDLE').upper(), 'created')

    def controller_mode_from_runtime_phase(self, runtime_phase: str) -> str:
        if runtime_phase in {'safe_stop', 'fault'}:
            return 'maintenance'
        if runtime_phase in {'perception', 'plan', 'execute', 'verify'}:
            return 'task'
        return 'idle'

    def build_task_status(self, *, current: TaskContext | None, phase: str, message: str, queue_depth: int, awaiting: dict[str, Any] | None, active_calibration_version: str, active_calibration_workspace: str, progress: float) -> dict[str, Any]:
        runtime_phase = self.runtime_phase_from_phase(phase)
        task_stage = self.task_stage_from_phase(phase)
        controller_mode = self.controller_mode_from_runtime_phase(runtime_phase)
        blocked = str(phase or '').upper() == 'BLOCKED_BY_PERCEPTION'
        return {
            'taskId': None if current is None else current.task_id,
            'taskType': None if current is None else current.task_type,
            'stage': phase,
            'taskStage': task_stage,
            'runtimePhase': runtime_phase,
            'controllerMode': controller_mode,
            'selectedTargetId': None if current is None else current.target_id,
            'placeProfile': None if current is None else current.place_profile,
            'graphKey': None if current is None else (current.metadata.get('graphKey') if isinstance(current.metadata, dict) else None),
            'activeGraphNode': None if current is None else (current.metadata.get('activeGraphNode') if isinstance(current.metadata, dict) else None),
            'activeGraphStage': None if current is None else (current.metadata.get('activeGraphStage') if isinstance(current.metadata, dict) else None),
            'retryCount': 0 if current is None else current.current_retry,
            'maxRetry': 0 if current is None else current.max_retry,
            'active': current is not None,
            'cancelRequested': False if current is None else bool(current.cancel_requested),
            'message': message,
            'progress': progress,
            'queueDepth': queue_depth,
            'awaiting': awaiting,
            'blocked': blocked,
            'blockedReason': message if blocked else '',
            'activeCalibrationVersion': active_calibration_version,
            'activeCalibrationWorkspace': active_calibration_workspace,
        }

    def build_runtime_summary(self, *, queue_depth: int, current: TaskContext | None, phase: str, awaiting: dict[str, Any] | None, tracker_count: int, last_feedback: dict[str, Any], mode: str, action_servers: dict[str, bool]) -> dict[str, Any]:
        runtime_phase = self.runtime_phase_from_phase(phase)
        task_stage = self.task_stage_from_phase(phase)
        controller_mode = self.controller_mode_from_runtime_phase(runtime_phase)
        blocked = str(phase or '').upper() == 'BLOCKED_BY_PERCEPTION'
        return {
            'queueDepth': queue_depth,
            'activeTask': None if current is None else current.task_id,
            'graphKey': None if current is None else (current.metadata.get('graphKey') if isinstance(current.metadata, dict) else None),
            'activeGraphNode': None if current is None else (current.metadata.get('activeGraphNode') if isinstance(current.metadata, dict) else None),
            'stage': phase,
            'taskStage': task_stage,
            'runtimePhase': runtime_phase,
            'controllerMode': controller_mode,
            'awaiting': awaiting,
            'blocked': blocked,
            'blockedReason': last_feedback.get('message', '') if blocked and isinstance(last_feedback, dict) else '',
            'trackerCount': tracker_count,
            'lastFeedback': last_feedback,
            'mode': mode,
            'actionServers': dict(action_servers),
        }
