from __future__ import annotations

"""Shared runtime-contract helpers for split-stack task planning and execution.

Planner/executor runtime transports still use plain serializable dictionaries for
backward-compatible ``std_msgs/String`` channels, but the stage schema itself is
now sourced from ``arm_backend_common.stage_plan.StagePlan`` so ``arm_common`` no
longer depends on the planner implementation package.
"""

from typing import Any

from arm_backend_common.data_models import CalibrationProfile, TargetSnapshot, TaskContext
from arm_backend_common.stage_plan import StagePlan


def stage_plan_to_dict(stage: StagePlan) -> dict[str, Any]:
    """Serialize a :class:`StagePlan` into a plain dictionary.

    Args:
        stage: Shared stage-plan contract.

    Returns:
        dict[str, Any]: JSON-safe stage payload.

    Raises:
        Does not raise.
    """
    return {'name': str(stage.name), 'kind': str(stage.kind), 'payload': dict(stage.payload)}


def stage_plan_from_dict(payload: dict[str, Any]) -> StagePlan:
    """Deserialize a plain dictionary into a :class:`StagePlan`.

    Args:
        payload: Serialized stage payload.

    Returns:
        StagePlan: Shared stage-plan contract.

    Raises:
        Does not raise. Missing fields degrade to safe defaults.
    """
    return StagePlan(
        name=str(payload.get('name', '')),
        kind=str(payload.get('kind', '')),
        payload=dict(payload.get('payload') or {}),
    )


def build_planning_request(*, request_id: str, context: TaskContext, target: TargetSnapshot, calibration: CalibrationProfile, correlation_id: str = '', task_run_id: str = '') -> dict[str, Any]:
    """Build the split-stack planning request payload."""
    return {
        'requestId': str(request_id),
        'correlationId': str(correlation_id),
        'taskRunId': str(task_run_id),
        'taskId': str(context.task_id),
        'context': {
            'task_id': str(context.task_id),
            'task_type': str(context.task_type),
            'target_selector': str(context.target_selector),
            'place_profile': str(context.place_profile),
            'active_place_pose': dict(context.active_place_pose),
        },
        'target': target.to_dict(),
        'calibration': calibration.to_dict(),
    }


def build_planning_result(*, request_id: str, task_id: str, accepted: bool, message: str, plan: list[StagePlan] | None = None, correlation_id: str = '', task_run_id: str = '') -> dict[str, Any]:
    """Build the split-stack planning result payload."""
    return {
        'requestId': str(request_id),
        'correlationId': str(correlation_id),
        'taskRunId': str(task_run_id),
        'taskId': str(task_id),
        'accepted': bool(accepted),
        'message': str(message),
        'stages': [stage_plan_to_dict(stage) for stage in list(plan or [])],
    }


def build_execution_request(*, request_id: str, task_id: str, plan: list[StagePlan], correlation_id: str = '', task_run_id: str = '') -> dict[str, Any]:
    """Build the split-stack execution request payload."""
    return {
        'requestId': str(request_id),
        'correlationId': str(correlation_id),
        'taskRunId': str(task_run_id),
        'task_id': str(task_id),
        'stages': [stage_plan_to_dict(stage) for stage in plan],
    }


def build_execution_status(*, request_id: str, task_id: str, status: str, message: str, stage_name: str = '', command_id: str = '', correlation_id: str = '', task_run_id: str = '') -> dict[str, Any]:
    """Build the split-stack execution status payload."""
    return {
        'requestId': str(request_id),
        'correlationId': str(correlation_id),
        'taskRunId': str(task_run_id),
        'taskId': str(task_id),
        'status': str(status),
        'message': str(message),
        'stageName': str(stage_name),
        'commandId': str(command_id),
    }
