from __future__ import annotations

import time

from arm_backend_common.data_models import CalibrationProfile, HardwareSnapshot, TargetSnapshot, TaskProfile, TaskRequest
from arm_task_orchestrator.execution_adapter import ExecutionAdapter
from arm_task_orchestrator.fault_manager import FaultManager
from arm_task_orchestrator.runtime import RuntimeHooks, TaskRuntimeEngine, TaskRuntimeState
from arm_task_orchestrator.stack_factory import build_application_service, build_target_tracker
from arm_task_orchestrator.state_machine import SystemStateMachine
from arm_task_orchestrator.task_plugins import resolve_task_graph_contract
from arm_task_orchestrator.verification import VerificationManager


def _build_engine() -> TaskRuntimeEngine:
    task_profile = TaskProfile(selector_to_place_profile={'red': 'bin_red'}, verify_timeout_sec=0.2)
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
    engine.update_hardware(HardwareSnapshot(stm32_online=True, home_ok=True, gripper_ok=True, updated_monotonic=time.monotonic()))
    engine.update_calibration(CalibrationProfile(place_profiles={'bin_red': {'x': 0.2, 'y': 0.0, 'yaw': 0.0}}))
    engine.update_readiness_snapshot({'modeReady': True, 'allReady': True, 'commandPolicies': {'startTask': {'allowed': True, 'reason': 'ready'}}})
    return engine


def test_runtime_updates_task_graph_stage_across_plan_execute_verify_complete() -> None:
    engine = _build_engine()
    contract = resolve_task_graph_contract('PICK_AND_PLACE', target_selector='red')
    request = TaskRequest(task_id='task-graph', task_type='PICK_AND_PLACE', target_selector='red', metadata=contract)
    engine.enqueue_task_request(request, hardware_fresh_sec=5.0)
    engine.tick(hardware_fresh_sec=5.0, command_timeout_sec=1.0, perception_blocked_after_sec=0.2)
    assert engine.state.current is not None
    assert engine.state.current.metadata['activeGraphStage'] == 'perception'
    engine.update_target(TargetSnapshot(target_id='target-1', target_type='cube', semantic_label='red', table_x=0.1, table_y=0.1, yaw=0.0, confidence=0.95, received_monotonic=time.monotonic()))
    engine.tick(hardware_fresh_sec=5.0, command_timeout_sec=1.0, perception_blocked_after_sec=0.2)
    assert engine.state.current.metadata['activeGraphStage'] == 'planning'
    pending_plan = engine.state.pending_plan_request_id
    engine.update_plan_result({'requestId': pending_plan, 'taskId': 'task-graph', 'accepted': True, 'message': 'plan ok', 'stages': [{'name': 'go_home', 'kind': 'connector', 'payload': {'named_pose': 'home'}}]})
    engine.tick(hardware_fresh_sec=5.0, command_timeout_sec=1.0, perception_blocked_after_sec=0.2)
    assert engine.state.current.metadata['activeGraphStage'] == 'execution'
    pending_exec = engine.state.pending_execution_request_id
    engine.update_execution_status({'requestId': pending_exec, 'taskId': 'task-graph', 'status': 'done', 'message': 'execution done'})
    engine.tick(hardware_fresh_sec=5.0, command_timeout_sec=1.0, perception_blocked_after_sec=0.2)
    assert engine.state.current.metadata['activeGraphStage'] == 'verification'
    engine.update_target(TargetSnapshot(target_id='target-1', target_type='cube', semantic_label='red', table_x=0.1, table_y=0.1, yaw=0.0, confidence=0.95, received_monotonic=0.0))
    engine.tick(hardware_fresh_sec=5.0, command_timeout_sec=1.0, perception_blocked_after_sec=0.2)
    assert engine.state.current is None
    outcome = engine.state.task_outcomes['task-graph']
    assert outcome['state'] == 'succeeded'
