import pytest

from arm_motion_planner.errors import InvalidTargetError, WorkspaceViolationError
from arm_motion_planner.planner import MotionPlanner
from arm_backend_common.data_models import CalibrationProfile, TargetSnapshot, TaskContext


def test_motion_planner_rejects_invalid_targets_with_specific_errors():
    planner = MotionPlanner(workspace=(-0.1, 0.1, -0.1, 0.1))
    calibration = CalibrationProfile(place_profiles={'default': {'x': 0.0, 'y': 0.0, 'yaw': 0.0}})
    context = TaskContext(task_id='task-1', task_type='pick_place')
    with pytest.raises(InvalidTargetError):
        planner.build_pick_place_plan(context, TargetSnapshot(target_id='t1', confidence=0.1), calibration)
    with pytest.raises(WorkspaceViolationError):
        planner.build_pick_place_plan(context, TargetSnapshot(target_id='t1', confidence=0.9, table_x=0.5), calibration)
