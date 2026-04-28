from __future__ import annotations

from arm_backend_common.data_models import HardwareSnapshot, TaskProfile, TaskRequest
from arm_task_orchestrator.execution_adapter import ExecutionAdapter
from arm_task_orchestrator.fault_manager import FaultManager
from arm_task_orchestrator.runtime import RuntimeHooks, TaskRuntimeEngine, TaskRuntimeState
from arm_task_orchestrator.stack_factory import build_application_service, build_target_tracker
from arm_task_orchestrator.state_machine import SystemStateMachine
from arm_task_orchestrator.verification import VerificationManager


def _build_engine() -> TaskRuntimeEngine:
    task_profile = TaskProfile(selector_to_place_profile={'red': 'bin_red'})
    execution = ExecutionAdapter()
    fault_manager = FaultManager()
    _, application = build_application_service(task_profile, execution, VerificationManager(), fault_manager)
    tracker = build_target_tracker(task_profile, stable_seen_count=1)
    state = TaskRuntimeState(task_profile=task_profile)
    hooks = RuntimeHooks(
        emit_event=lambda *args, **kwargs: None,
        send_hardware_command=lambda payload: None,
        publish_selected_target=lambda payload: None,
        publish_fault=lambda code, task_id, message: None,
        publish_planning_request=lambda payload: None,
        publish_execution_request=lambda payload: None,
    )
    engine = TaskRuntimeEngine(
        state_machine=SystemStateMachine(),
        application=application,
        execution_adapter=execution,
        fault_manager=fault_manager,
        tracker=tracker,
        state=state,
        hooks=hooks,
    )
    engine.update_hardware(HardwareSnapshot(stm32_online=True, home_ok=True, gripper_ok=True, updated_monotonic=1.0))
    return engine


def test_runtime_rejects_task_without_authoritative_readiness_snapshot():
    engine = _build_engine()
    decision = engine.admission_decision(TaskRequest(task_id='task-1', task_type='pick_place', target_selector='red'), hardware_fresh_sec=1.0)
    assert decision.accepted is False
    assert decision.message == 'task execution requires authoritative readiness snapshot'


def test_runtime_rejects_task_when_authoritative_readiness_blocks_start_task():
    engine = _build_engine()
    engine.update_readiness_snapshot({
        'modeReady': False,
        'allReady': False,
        'commandPolicies': {
            'startTask': {'allowed': False, 'reason': 'missing readiness: camera_alive(perception offline)'}
        },
    })
    decision = engine.admission_decision(TaskRequest(task_id='task-2', task_type='pick_place', target_selector='red'), hardware_fresh_sec=1.0)
    assert decision.accepted is False
    assert decision.message == 'missing readiness: camera_alive(perception offline)'


def test_runtime_accepts_task_when_authoritative_readiness_allows_start_task():
    engine = _build_engine()
    engine.update_readiness_snapshot({
        'modeReady': True,
        'allReady': True,
        'commandPolicies': {
            'startTask': {'allowed': True, 'reason': 'ready'}
        },
    })
    decision = engine.enqueue_task_request(TaskRequest(task_id='task-3', task_type='pick_place', target_selector='red'), hardware_fresh_sec=1.0)
    assert decision.accepted is True
    assert engine.state.queue
    assert engine.state.queue[0].task_id == 'task-3'



def test_runtime_rejects_task_when_readiness_snapshot_is_stale():
    engine = _build_engine()
    engine.update_readiness_snapshot({
        'modeReady': True,
        'allReady': True,
        'commandPolicies': {
            'startTask': {'allowed': True, 'reason': 'ready'}
        },
    })
    engine.state.readiness_received_monotonic -= 5.0
    decision = engine.admission_decision(TaskRequest(task_id='task-4', task_type='pick_place', target_selector='red'), hardware_fresh_sec=0.5)
    assert decision.accepted is False
    assert decision.message == 'authoritative readiness snapshot stale'


def test_runtime_exposes_named_command_policy_decision():
    engine = _build_engine()
    engine.update_readiness_snapshot({
        'modeReady': False,
        'allReady': False,
        'commandPolicies': {
            'home': {'allowed': False, 'reason': 'home blocked by maintenance policy'}
        },
    })
    decision = engine.command_policy_decision('home', hardware_fresh_sec=1.0)
    assert decision.accepted is False
    assert decision.message == 'home blocked by maintenance policy'
