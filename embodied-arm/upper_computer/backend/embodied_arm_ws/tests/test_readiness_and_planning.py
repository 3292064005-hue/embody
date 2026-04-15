from arm_backend_common.data_models import CalibrationProfile, HardwareSnapshot, TargetSnapshot, TaskProfile, TaskRequest
from arm_backend_common.enums import FaultCode
from arm_motion_executor import MotionExecutor
from arm_motion_planner import MotionPlanner
from arm_perception import VisionTargetTracker
from arm_readiness_manager import ReadinessManager
from arm_task_orchestrator.orchestrator import TaskOrchestrator


def test_readiness_manager_blocks_until_all_ready():
    manager = ReadinessManager(checks=('ros2', 'hardware_bridge'))
    manager.update('ros2', True, 'ok')
    ok, reason = manager.is_ready_for_task()
    assert not ok
    assert 'hardware_bridge' in reason
    manager.update('hardware_bridge', True, 'ok')
    ok, reason = manager.is_ready_for_manual()
    assert ok
    assert reason == 'ready'


def test_planner_executor_pipeline():
    planner = MotionPlanner()
    executor = MotionExecutor()
    calibration = CalibrationProfile(place_profiles={'default': {'x': 0.2, 'y': 0.1, 'yaw': 0.0}})
    request = TaskRequest(task_id='t1', task_type='PICK_AND_PLACE', target_selector='red')
    orchestrator = TaskOrchestrator(TaskProfile(confidence_threshold=0.5))
    context = orchestrator.begin_context(request)
    target = TargetSnapshot(target_id='a', target_type='cube', semantic_label='red', table_x=0.1, table_y=0.2, confidence=0.95)
    context = orchestrator.bind_target(context, target, calibration)
    plan = planner.build_pick_place_plan(context, target, calibration)
    result = executor.validate(plan)
    assert result.accepted
    commands = executor.build_command_stream(plan, context.task_id)
    assert commands[0]['kind'] == 'EXEC_STAGE'
    assert commands[-1]['kind'] == 'HOME'
    assert len(commands) == 8


def test_target_tracker_prunes_stale_entries_and_honors_seen_count():
    tracker = VisionTargetTracker(stale_after_sec=1.0, min_seen_count=2)
    target = TargetSnapshot(target_id='a', target_type='cube', semantic_label='red', confidence=0.7)
    tracker.upsert(target, now=1.0)
    assert tracker.get_graspable() == []
    tracker.upsert(target, now=1.1)
    assert len(tracker.get_graspable()) == 1
    tracker.prune(now=2.5)
    assert tracker.get_graspable() == []


def test_orchestrator_checks_hardware_readiness_and_retry():
    orchestrator = TaskOrchestrator(TaskProfile())
    decision = orchestrator.verify_hardware_ready(HardwareSnapshot(stm32_online=False))
    assert not decision.accepted
    ctx = orchestrator.begin_context(TaskRequest(task_id='t1', task_type='pick', max_retry=1, auto_retry=True))
    retry = orchestrator.decide_retry(ctx, fault=FaultCode.TARGET_NOT_FOUND, message='retry me')
    assert retry.accepted
    fail = orchestrator.decide_retry(ctx, fault=FaultCode.TARGET_NOT_FOUND, message='stop now')
    assert not fail.accepted
