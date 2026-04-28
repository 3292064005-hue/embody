from arm_backend_common.data_models import CalibrationProfile, HardwareSnapshot, TargetSnapshot, TaskContext, TaskProfile, TaskRequest
from arm_backend_common.enums import FaultCode
from arm_motion_executor.executor import MotionExecutor
from arm_motion_planner.planner import MotionPlanner
from arm_perception.target_tracker import VisionTargetTracker
from arm_readiness_manager.readiness import ReadinessManager
from arm_task_orchestrator.orchestrator import TaskOrchestrator
from arm_task_orchestrator.task_plugins import resolve_task_runtime_plugin


def test_readiness_check_becomes_stale_without_refresh():
    manager = ReadinessManager()
    manager.update('task_orchestrator', True, 'online', stale_after_sec=0.1)
    snapshot = manager.snapshot('idle')
    check = snapshot.checks['task_orchestrator']
    assert check.effective_ok(now=check.updated_monotonic + 0.05)
    assert not check.effective_ok(now=check.updated_monotonic + 0.2)


def test_tracker_resets_seen_count_when_target_moves():
    tracker = VisionTargetTracker(min_seen_count=2)
    tracker.upsert(TargetSnapshot(target_id='t1', target_type='cube', semantic_label='red', table_x=0.1, table_y=0.1, confidence=0.9), now=1.0)
    tracker.upsert(TargetSnapshot(target_id='t1', target_type='cube', semantic_label='red', table_x=0.1, table_y=0.1, confidence=0.92), now=1.1)
    assert tracker.select('red', now=1.1) is not None
    tracker.upsert(TargetSnapshot(target_id='t1', target_type='cube', semantic_label='red', table_x=0.25, table_y=0.1, confidence=0.93), now=1.2)
    assert tracker.select('red', now=1.2) is None
    tracker.upsert(TargetSnapshot(target_id='t1', target_type='cube', semantic_label='red', table_x=0.25, table_y=0.1, confidence=0.95), now=1.3)
    assert tracker.select('red', now=1.3) is not None


def test_orchestrator_skips_completed_and_stale_targets():
    profile = TaskProfile(confidence_threshold=0.8, stale_target_sec=0.5)
    orchestrator = TaskOrchestrator(profile)
    fresh = TargetSnapshot(target_id='fresh', target_type='cube', semantic_label='red', confidence=0.9, received_monotonic=10.0)
    stale = TargetSnapshot(target_id='stale', target_type='cube', semantic_label='red', confidence=0.99, received_monotonic=1.0)
    target = orchestrator.select_target([stale, fresh], 'red', now=10.2, exclude_keys={'fresh'})
    assert target is None
    target = orchestrator.select_target([stale, fresh], 'red', now=10.2)
    assert target.target_id == 'fresh'


def test_task_plugin_registry_maps_clear_table_to_continuous():
    plugin = resolve_task_runtime_plugin('CLEAR_TABLE')
    assert plugin.key == 'continuous'


def test_planner_and_executor_validate_full_pick_place_plan():
    planner = MotionPlanner()
    executor = MotionExecutor()
    target = TargetSnapshot(target_id='t1', target_type='cube', semantic_label='red', table_x=0.1, table_y=0.2, yaw=0.0, confidence=0.95)
    calibration = CalibrationProfile(place_profiles={'default': {'x': 0.2, 'y': 0.0, 'yaw': 0.0}, 'bin_red': {'x': 0.25, 'y': 0.12, 'yaw': 0.0}})
    context = TaskContext(task_id='task-1', task_type='PICK_AND_PLACE', place_profile='bin_red', active_place_pose=calibration.resolve_place_profile('bin_red'))
    plan = planner.build_pick_place_plan(context, target, calibration)
    result = executor.validate(plan)
    assert result.accepted, result.message
    commands = executor.build_command_stream(plan, 'task-1')
    assert commands[0]['kind'] == 'EXEC_STAGE'
    assert commands[2]['kind'] == 'CLOSE_GRIPPER'
    assert commands[-1]['kind'] == 'HOME'
