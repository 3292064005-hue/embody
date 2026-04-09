from arm_backend_common.data_models import CalibrationProfile, HardwareSnapshot, TargetSnapshot, TaskProfile, TaskRequest
from arm_backend_common.enums import FaultCode
from arm_motion_executor import MotionExecutor
from arm_motion_planner import MotionPlanner
from arm_task_orchestrator import FaultManager, PlanningAdapter, TaskApplicationService, TaskOrchestrator
from arm_task_orchestrator.execution_adapter import ExecutionAdapter
from arm_task_orchestrator.verification import VerificationManager


def _build_service() -> TaskApplicationService:
    profile = TaskProfile(confidence_threshold=0.5)
    orchestrator = TaskOrchestrator(profile)
    planner = MotionPlanner()
    executor = MotionExecutor()
    verification = VerificationManager()
    return TaskApplicationService(orchestrator, PlanningAdapter(planner, executor), ExecutionAdapter(), verification, FaultManager(), profile)


def test_application_service_binds_target_and_returns_execution_bundle():
    service = _build_service()
    context = service.begin_task(TaskRequest(task_id='svc-1', task_type='pick_place', target_selector='red'))
    target = TargetSnapshot(target_id='red-1', target_type='cube', semantic_label='red', table_x=0.1, table_y=0.0, confidence=0.99)
    calibration = CalibrationProfile(place_profiles={'default': {'x': 0.2, 'y': 0.1, 'yaw': 0.0}})
    result = service.bind_and_plan(context, target, calibration)
    assert result.accepted
    assert len(result.plan) == 8
    assert result.commands[0]['kind'] == 'EXEC_STAGE'


def test_application_service_returns_retryable_fault_when_verification_fails():
    service = _build_service()
    context = service.begin_task(TaskRequest(task_id='svc-2', task_type='pick_place', target_selector='red', auto_retry=True, max_retry=1))
    target = TargetSnapshot(target_id='red-1', target_type='cube', semantic_label='red', table_x=0.1, table_y=0.0, confidence=0.99)
    context.selected_target = target
    decision = service.verify_outcome(context, HardwareSnapshot(stm32_online=True), target, now=context.start_monotonic + 10.0)
    assert decision.finished
    assert not decision.success
    assert decision.fault == FaultCode.TARGET_STALE
