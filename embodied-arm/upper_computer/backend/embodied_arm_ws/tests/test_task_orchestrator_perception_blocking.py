from __future__ import annotations

from arm_backend_common.data_models import TaskProfile, TaskRequest
from arm_task_orchestrator.execution_adapter import ExecutionAdapter
from arm_task_orchestrator.fault_manager import FaultManager
from arm_task_orchestrator.runtime import RuntimeHooks, TaskRuntimeEngine, TaskRuntimeState
from arm_task_orchestrator.stack_factory import build_application_service, build_target_tracker
from arm_task_orchestrator.state_machine import SystemStateMachine
from arm_task_orchestrator.verification import VerificationManager
import time


class EventLog(list):
    def __call__(self, level, source, event_type, task_id, code, message, **kwargs):
        self.append({'level': level, 'source': source, 'event_type': event_type, 'task_id': task_id, 'code': code, 'message': message, 'kwargs': kwargs})


def test_runtime_blocks_when_no_authoritative_target_arrives():
    task_profile = TaskProfile(selector_to_place_profile={'red': 'bin_red'}, verify_timeout_sec=0.2)
    execution = ExecutionAdapter()
    fault_manager = FaultManager()
    _, application = build_application_service(task_profile, execution, VerificationManager(), fault_manager)
    tracker = build_target_tracker(task_profile, stable_seen_count=1)
    state = TaskRuntimeState(task_profile=task_profile)
    events = EventLog()
    published = {'faults': [], 'targets': [], 'plans': [], 'execs': [], 'commands': []}
    hooks = RuntimeHooks(
        emit_event=events,
        send_hardware_command=lambda payload: published['commands'].append(payload),
        publish_selected_target=lambda payload: published['targets'].append(payload),
        publish_fault=lambda code, task_id, message: published['faults'].append((code, task_id, message)),
        publish_planning_request=lambda payload: published['plans'].append(payload),
        publish_execution_request=lambda payload: published['execs'].append(payload),
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
    state.queue.append(TaskRequest(task_id='task-block', task_type='pick_place', target_selector='red', request_id='req-task-block', correlation_id='corr-task-block', task_run_id='run-task-block'))
    engine.tick(hardware_fresh_sec=1.0, command_timeout_sec=1.0, perception_blocked_after_sec=0.01)
    assert state.current is not None
    state.current.perception_deadline = time.monotonic() - 1.0
    engine.tick(hardware_fresh_sec=1.0, command_timeout_sec=1.0, perception_blocked_after_sec=0.1)
    assert engine.state.current is not None
    assert engine.state.current.last_message == 'No authoritative target available'
    assert engine.state.current.task_id == 'task-block'
    assert any(item['event_type'] == 'BLOCKED_BY_PERCEPTION' for item in events)
