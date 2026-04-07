from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from arm_backend_common.data_models import CalibrationProfile, TargetSnapshot, TaskContext
from arm_backend_common.enums import FaultCode
from arm_motion_executor import MotionExecutor
from arm_motion_planner import MotionPlanner


@dataclass
class PlanningResult:
    accepted: bool
    message: str
    plan: list[Any]
    commands: list[dict[str, Any]]
    fault: FaultCode = FaultCode.NONE


class PlanningAdapter:
    """Bridge task context planning to executor-ready command streams."""

    def __init__(self, planner: MotionPlanner, executor: MotionExecutor) -> None:
        self._planner = planner
        self._executor = executor

    def build_execution_bundle(self, context: TaskContext, target: TargetSnapshot, calibration: CalibrationProfile) -> PlanningResult:
        """Create and validate a command bundle for the current task context.

        Args:
            context: Active task context.
            target: Selected target snapshot.
            calibration: Active calibration profile.

        Returns:
            PlanningResult carrying plan stages and executor commands.
        """
        try:
            plan = self._planner.build_pick_place_plan(context, target, calibration)
            validation = self._executor.validate(plan)
        except Exception as exc:
            return PlanningResult(False, str(exc), [], [], FaultCode.PLAN_FAILED)
        if not validation.accepted:
            return PlanningResult(False, validation.message, plan, [], FaultCode.PLAN_FAILED)
        commands = self._executor.build_command_stream(plan, context.task_id)
        return PlanningResult(True, validation.message, plan, commands)
