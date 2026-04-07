from arm_backend_common.data_models import CalibrationProfile, TargetSnapshot, TaskProfile, TaskRequest
from arm_motion_executor import MotionExecutor
from arm_motion_planner import MotionPlanner
from arm_task_orchestrator import TaskOrchestrator


def test_orchestrator_binds_target_and_marks_complete():
    calibration = CalibrationProfile(place_profiles={'bin_red': {'x': 0.1, 'y': 0.2, 'yaw': 0.0}})
    profile = TaskProfile(confidence_threshold=0.6)
    orchestrator = TaskOrchestrator(profile)
    request = TaskRequest(task_id='abc', task_type='pick', target_selector='red', place_profile='bin_red')
    context = orchestrator.begin_context(request)
    target = TargetSnapshot(target_id='red-1', target_type='cube', semantic_label='red', table_x=0.05, table_y=0.02, confidence=0.91)
    bound = orchestrator.bind_target(context, target, calibration)
    assert bound.target_id == 'red-1'
    assert bound.stage == 'planning'
    done = orchestrator.complete(bound, 'done')
    assert done.accepted
    assert bound.complete_count == 1
    assert 'red-1' in bound.completed_target_ids


def test_planner_rejects_out_of_workspace_target():
    planner = MotionPlanner(workspace=(-0.1, 0.1, -0.1, 0.1))
    request = TaskRequest(task_id='t1', task_type='pick', target_selector='red')
    orchestrator = TaskOrchestrator(TaskProfile(confidence_threshold=0.5))
    context = orchestrator.begin_context(request)
    target = TargetSnapshot(target_id='bad', target_type='cube', semantic_label='red', table_x=0.5, table_y=0.2, confidence=0.99)
    try:
        planner.build_pick_place_plan(context, target, CalibrationProfile())
    except ValueError as exc:
        assert 'workspace' in str(exc)
    else:
        raise AssertionError('expected workspace validation error')


def test_executor_rejects_wrong_stage_order():
    executor = MotionExecutor()
    bad_plan = []
    result = executor.validate(bad_plan)
    assert not result.accepted
