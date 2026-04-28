from __future__ import annotations

import time

from arm_backend_common.data_models import CalibrationProfile, HardwareSnapshot, TargetSnapshot, TaskProfile, TaskRequest
from arm_task_orchestrator.execution_adapter import ExecutionAdapter
from arm_task_orchestrator.fault_manager import FaultManager
from arm_task_orchestrator.runtime import RuntimeHooks, TaskRuntimeEngine, TaskRuntimeState
from arm_task_orchestrator.stack_factory import build_application_service, build_runtime_engine, build_target_tracker
from arm_task_orchestrator.state_machine import SystemStateMachine
from arm_task_orchestrator.task_plugins import DEFAULT_STAGE_CONTRACTS, resolve_task_graph_contract
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
    engine = build_runtime_engine(
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


def test_runtime_engine_exposes_behavior_tree_state_on_main_task_path() -> None:
    engine = _build_engine()
    contract = resolve_task_graph_contract('PICK_AND_PLACE', target_selector='red')
    request = TaskRequest(task_id='task-bt', task_type='PICK_AND_PLACE', target_selector='red', metadata=contract)
    engine.enqueue_task_request(request, hardware_fresh_sec=5.0)
    engine.tick(hardware_fresh_sec=5.0, command_timeout_sec=1.0, perception_blocked_after_sec=0.2)
    assert engine.state.current is not None
    assert engine.state.bt_last_status == 'RUNNING'
    assert engine.state.bt_status_by_node['dispatch_perception'] == 'RUNNING'
    assert isinstance(engine.state.current.metadata.get('behaviorTree'), dict)
    assert engine.state.current.metadata['behaviorTree']['policy']['maxAutomaticRetry'] >= 1

    engine.update_target(TargetSnapshot(target_id='target-bt', target_type='cube', semantic_label='red', table_x=0.1, table_y=0.1, yaw=0.0, confidence=0.95, received_monotonic=time.monotonic()))
    engine.tick(hardware_fresh_sec=5.0, command_timeout_sec=1.0, perception_blocked_after_sec=0.2)
    assert engine.state.bt_status_by_node['dispatch_perception'] == 'SUCCESS'
    assert engine.state.bt_status_by_node['dispatch_plan'] == 'SUCCESS'

    pending_plan = engine.state.pending_plan_request_id
    engine.update_plan_result({'requestId': pending_plan, 'taskId': 'task-bt', 'accepted': True, 'message': 'plan ok', 'stages': [{'name': 'go_home', 'kind': 'connector', 'payload': {'named_pose': 'home'}}]})
    engine.tick(hardware_fresh_sec=5.0, command_timeout_sec=1.0, perception_blocked_after_sec=0.2)
    assert engine.state.bt_status_by_node['dispatch_execute'] == 'SUCCESS'
    assert engine.state.bt_tick_count >= 3


class _HookedSelector:
    def select_target(self, engine):
        current = engine.state.current
        if current is None:
            return None
        return engine.tracker.select(current.target_selector, exclude_keys=current.completed_target_ids)


class _HookedStagePolicy:
    def on_plan_accepted(self, engine, payload, *, contract):
        current = engine.state.current
        assert current is not None
        assert contract.stage == 'planning'
        current.metadata['planHookSeen'] = payload.get('message')
        engine._state_machine.plan_ok('plan hook consumed')
        engine._publish_execution_request(command_timeout_sec=1.0)
        return True

    def on_execution_success(self, engine, payload, *, contract):
        current = engine.state.current
        assert current is not None
        assert contract.stage == 'execution'
        current.metadata['executionHookSeen'] = payload.get('status')
        engine._state_machine.execute_ok('execution hook consumed')
        engine._set_graph_node(kind='verification', default_stage='verification')
        engine.state.current.verify_deadline = time.monotonic() + engine.state.task_profile.verify_timeout_sec
        return True

    def on_verify_success(self, engine, message, *, perception_blocked_after_sec, contract):
        del engine, message, perception_blocked_after_sec
        assert contract.stage == 'verification'
        return False


class _HookedRecoveryPolicy:
    def on_retryable_fault(self, engine, *, message, perception_blocked_after_sec, contract):
        del engine, message, perception_blocked_after_sec
        assert contract.stage == 'verification'
        return False


class _HookedPlugin:
    key = 'hooked'

    def __init__(self):
        self.target_selector = _HookedSelector()
        self.stage_policy = _HookedStagePolicy()
        self.recovery_policy = _HookedRecoveryPolicy()

    def stage_contract(self, stage):
        return DEFAULT_STAGE_CONTRACTS.get(stage, DEFAULT_STAGE_CONTRACTS['verification'])


def test_runtime_plugin_stage_hooks_can_consume_plan_and_execution(monkeypatch) -> None:
    import arm_task_orchestrator.runtime as runtime_module

    engine = _build_engine()
    monkeypatch.setattr(runtime_module, 'resolve_task_runtime_plugin', lambda *_args, **_kwargs: _HookedPlugin())
    contract = resolve_task_graph_contract('PICK_AND_PLACE', target_selector='red')
    request = TaskRequest(task_id='task-hooked', task_type='PICK_AND_PLACE', target_selector='red', metadata=contract)
    engine.enqueue_task_request(request, hardware_fresh_sec=5.0)
    engine.tick(hardware_fresh_sec=5.0, command_timeout_sec=1.0, perception_blocked_after_sec=0.2)
    engine.update_target(TargetSnapshot(target_id='target-hooked', target_type='cube', semantic_label='red', table_x=0.1, table_y=0.1, yaw=0.0, confidence=0.95, received_monotonic=time.monotonic()))
    engine.tick(hardware_fresh_sec=5.0, command_timeout_sec=1.0, perception_blocked_after_sec=0.2)
    pending_plan = engine.state.pending_plan_request_id
    engine.update_plan_result({'requestId': pending_plan, 'taskId': 'task-hooked', 'accepted': True, 'message': 'plan from hook', 'stages': [{'name': 'go_home', 'kind': 'connector', 'payload': {'named_pose': 'home'}}]})
    engine.tick(hardware_fresh_sec=5.0, command_timeout_sec=1.0, perception_blocked_after_sec=0.2)
    assert engine.state.current is not None
    assert engine.state.current.metadata['planHookSeen'] == 'plan from hook'
    assert engine.state.current.metadata['activeGraphStage'] == 'execution'
    pending_exec = engine.state.pending_execution_request_id
    engine.update_execution_status({'requestId': pending_exec, 'taskId': 'task-hooked', 'status': 'done', 'message': 'execution done'})
    engine.tick(hardware_fresh_sec=5.0, command_timeout_sec=1.0, perception_blocked_after_sec=0.2)
    assert engine.state.current is not None
    assert engine.state.current.metadata['executionHookSeen'] == 'done'
    assert engine.state.current.metadata['activeGraphStage'] == 'verification'


def _build_continuous_engine() -> TaskRuntimeEngine:
    task_profile = TaskProfile(selector_to_place_profile={'red': 'bin_red', 'blue': 'bin_red'}, verify_timeout_sec=0.2, clear_table_max_items=3)
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
    engine = build_runtime_engine(
        state_machine=SystemStateMachine(),
        application=application,
        execution_adapter=execution,
        fault_manager=fault_manager,
        tracker=tracker,
        state=state,
        hooks=hooks,
    )
    engine.update_hardware(HardwareSnapshot(stm32_online=True, home_ok=True, gripper_ok=True, updated_monotonic=time.monotonic()))
    engine.update_calibration(CalibrationProfile(place_profiles={'default': {'x': 0.2, 'y': 0.0, 'yaw': 0.0}, 'bin_red': {'x': 0.2, 'y': 0.0, 'yaw': 0.0}}))
    engine.update_readiness_snapshot({'modeReady': True, 'allReady': True, 'commandPolicies': {'startTask': {'allowed': True, 'reason': 'ready'}}})
    return engine


def _drive_continuous_task_to_verify(engine: TaskRuntimeEngine, *, task_id: str, first: TargetSnapshot, second: TargetSnapshot) -> None:
    contract = resolve_task_graph_contract('CLEAR_TABLE')
    request = TaskRequest(task_id=task_id, task_type='CLEAR_TABLE', metadata=contract)
    engine.enqueue_task_request(request, hardware_fresh_sec=5.0)
    engine.tick(hardware_fresh_sec=5.0, command_timeout_sec=1.0, perception_blocked_after_sec=0.2)
    engine.update_target(first)
    engine.update_target(second)
    engine.tick(hardware_fresh_sec=5.0, command_timeout_sec=1.0, perception_blocked_after_sec=0.2)
    pending_plan = engine.state.pending_plan_request_id
    engine.update_plan_result({'requestId': pending_plan, 'taskId': task_id, 'accepted': True, 'message': 'plan ok', 'stages': [{'name': 'go_home', 'kind': 'connector', 'payload': {'named_pose': 'home'}}]})
    engine.tick(hardware_fresh_sec=5.0, command_timeout_sec=1.0, perception_blocked_after_sec=0.2)
    pending_exec = engine.state.pending_execution_request_id
    engine.update_execution_status({'requestId': pending_exec, 'taskId': task_id, 'status': 'done', 'message': 'execution done'})
    engine.tick(hardware_fresh_sec=5.0, command_timeout_sec=1.0, perception_blocked_after_sec=0.2)
    assert engine.state.current is not None
    assert engine.state.current.metadata['activeGraphStage'] == 'verification'


def test_continuous_plugin_continues_to_next_target_after_verify_success() -> None:
    engine = _build_continuous_engine()
    now = time.monotonic()
    first = TargetSnapshot(target_id='target-a', target_type='cube', semantic_label='red', table_x=0.1, table_y=0.1, yaw=0.0, confidence=0.95, received_monotonic=now)
    second = TargetSnapshot(target_id='target-b', target_type='cube', semantic_label='blue', table_x=0.2, table_y=0.1, yaw=0.0, confidence=0.9, received_monotonic=now)
    _drive_continuous_task_to_verify(engine, task_id='clear-success', first=first, second=second)
    engine.update_target(TargetSnapshot(target_id='target-a', target_type='cube', semantic_label='red', table_x=0.1, table_y=0.1, yaw=0.0, confidence=0.95, received_monotonic=0.0))
    engine.update_target(TargetSnapshot(target_id='target-b', target_type='cube', semantic_label='blue', table_x=0.2, table_y=0.1, yaw=0.0, confidence=0.9, received_monotonic=time.monotonic()))
    engine.tick(hardware_fresh_sec=5.0, command_timeout_sec=1.0, perception_blocked_after_sec=0.2)
    assert engine.state.current is not None
    assert engine.state.current.task_id == 'clear-success'
    assert engine.state.current.metadata['activeGraphStage'] == 'perception'
    assert 'target-a' in engine.state.current.completed_target_ids
    assert engine.state.current.complete_count == 1
    engine.tick(hardware_fresh_sec=5.0, command_timeout_sec=1.0, perception_blocked_after_sec=0.2)
    assert engine.state.current is not None
    assert engine.state.current.selected_target is not None
    assert engine.state.current.selected_target.target_id == 'target-b'


def test_continuous_plugin_routes_retryable_fault_to_next_target() -> None:
    engine = _build_continuous_engine()
    now = time.monotonic()
    first = TargetSnapshot(target_id='target-r1', target_type='cube', semantic_label='red', table_x=0.1, table_y=0.1, yaw=0.0, confidence=0.95, received_monotonic=now)
    second = TargetSnapshot(target_id='target-r2', target_type='cube', semantic_label='blue', table_x=0.2, table_y=0.1, yaw=0.0, confidence=0.9, received_monotonic=now)
    _drive_continuous_task_to_verify(engine, task_id='clear-retry', first=first, second=second)
    engine.update_target(TargetSnapshot(target_id='target-r1', target_type='cube', semantic_label='red', table_x=0.1, table_y=0.1, yaw=0.0, confidence=0.95, received_monotonic=time.monotonic()))
    engine.update_target(TargetSnapshot(target_id='target-r2', target_type='cube', semantic_label='blue', table_x=0.2, table_y=0.1, yaw=0.0, confidence=0.9, received_monotonic=time.monotonic() - 10.0))
    current = engine.state.current
    assert current is not None
    engine.tick(hardware_fresh_sec=5.0, command_timeout_sec=1.0, perception_blocked_after_sec=0.2)
    assert engine.state.current is not None
    assert engine.state.current.task_id == 'clear-retry'
    assert engine.state.current.current_retry == 0
    assert engine.state.current.metadata['activeGraphStage'] == 'perception'
    assert 'target-r1' in engine.state.current.completed_target_ids
    engine.update_target(TargetSnapshot(target_id='target-r2', target_type='cube', semantic_label='blue', table_x=0.2, table_y=0.1, yaw=0.0, confidence=0.9, received_monotonic=time.monotonic()))
    engine.tick(hardware_fresh_sec=5.0, command_timeout_sec=1.0, perception_blocked_after_sec=0.2)
    assert engine.state.current is not None
    assert engine.state.current.selected_target is not None
    assert engine.state.current.selected_target.target_id == 'target-r2'
