from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from arm_motion_executor import MotionExecutor
from arm_motion_executor.motion_executor_node import MotionExecutorNode
from arm_motion_planner.planner import StagePlan
from arm_hardware_bridge import hardware_command_dispatcher_node as dispatcher_module
from arm_hardware_bridge.hardware_command_dispatcher_node import HardwareCommandDispatcherNode

ROOT = Path(__file__).resolve().parents[3]
MANIFEST_PATH = ROOT / 'docs' / 'generated' / 'runtime_contract_manifest.json'


class _Msg:
    def __init__(self, data: str):
        self.data = data


class _Logger:
    def __init__(self) -> None:
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def error(self, message: str) -> None:
        self.errors.append(str(message))

    def warn(self, message: str) -> None:
        self.warnings.append(str(message))



def _build_plan() -> list[StagePlan]:
    return [
        StagePlan('move_to_pregrasp', 'connector', {'x': 0.1, 'y': 0.0, 'z': 0.1, 'yaw': 0.0, 'timeoutSec': 1.0}),
        StagePlan('descend', 'propagator', {'x': 0.1, 'y': 0.0, 'z': 0.05, 'yaw': 0.0, 'timeoutSec': 1.0}),
        StagePlan('close_gripper', 'gripper', {'open': False, 'timeoutSec': 1.0}),
        StagePlan('lift', 'propagator', {'x': 0.1, 'y': 0.0, 'z': 0.1, 'yaw': 0.0, 'timeoutSec': 1.0}),
        StagePlan('move_to_place', 'connector', {'x': 0.2, 'y': 0.1, 'z': 0.05, 'yaw': 0.0, 'timeoutSec': 1.0}),
        StagePlan('open_gripper', 'gripper', {'open': True, 'timeoutSec': 1.0}),
        StagePlan('retreat', 'propagator', {'x': 0.2, 'y': 0.1, 'z': 0.1, 'yaw': 0.0, 'timeoutSec': 1.0}),
        StagePlan('go_home', 'connector', {'named_pose': 'home', 'timeoutSec': 1.0}),
    ]



def _runtime_request() -> dict[str, str]:
    return {
        'requestId': 'req-1',
        'taskId': 'task-1',
        'correlationId': 'corr-1',
        'taskRunId': 'run-1',
    }



def _build_active_node() -> tuple[SimpleNamespace, list[dict[str, str]], list[dict[str, str]]]:
    executor = MotionExecutor()
    commands = executor.build_command_stream(
        _build_plan(),
        'task-1',
        request_metadata={'request_id': 'req-1', 'correlation_id': 'corr-1', 'task_run_id': 'run-1'},
    )
    controller = MotionExecutorNode.__dict__  # silence lint; module import already validated
    del controller
    from arm_motion_executor.controller_adapter import ControllerAdapter

    adapter = ControllerAdapter()
    for command in commands[:2]:
        executor.dispatch_stage(command, started_monotonic=1.0)
        adapter.send_command(command)

    published: list[dict[str, str]] = []
    node = SimpleNamespace(
        _executor=executor,
        _controller=adapter,
        _active_runtime_request=_runtime_request(),
        _last_execution={},
        _parse_json=MotionExecutorNode._parse_json,
    )
    node._active_request_field = lambda name: MotionExecutorNode._active_request_field(node, name)
    node._publish_execution_status = lambda payload: published.append(payload)
    node._publish_active_terminal_status = lambda **kwargs: MotionExecutorNode._publish_active_terminal_status(node, **kwargs)
    node._mark_executor_fault = lambda **kwargs: MotionExecutorNode._mark_executor_fault(node, **kwargs)
    return node, commands, published



def test_executor_build_command_stream_propagates_request_correlation_metadata() -> None:
    executor = MotionExecutor()
    commands = executor.build_command_stream(
        _build_plan(),
        'task-closure',
        request_metadata={'request_id': 'req-42', 'correlation_id': 'corr-42', 'task_run_id': 'run-42'},
    )
    assert commands
    for command in commands:
        assert command['request_id'] == 'req-42'
        assert command['correlation_id'] == 'corr-42'
        assert command['task_run_id'] == 'run-42'



def test_fault_feedback_is_published_as_failed_terminal_status_and_clears_request() -> None:
    node, commands, published = _build_active_node()
    MotionExecutorNode._on_hardware_feedback(node, _Msg(json.dumps({
        'command_id': commands[0]['command_id'],
        'status': 'fault',
        'message': 'motor jam',
        'stage': commands[0]['stage'],
        'source': 'hardware_dispatcher',
    })))
    assert published
    assert published[0]['status'] == 'failed'
    assert published[0]['message'] == 'motor jam'
    assert published[0]['commandId'] == commands[0]['command_id']
    assert node._active_runtime_request == {}
    snapshot = node._executor.snapshot()
    assert snapshot['handles'][commands[0]['command_id']]['resultStatus'] == 'failed'



def test_fault_report_marks_active_handles_failed_and_publishes_business_failure() -> None:
    node, commands, published = _build_active_node()
    fault = SimpleNamespace(code=7, source='stm32', severity='critical', task_id='task-1', message='drive fault')
    MotionExecutorNode._on_fault_report(node, fault)
    assert published
    assert published[0]['status'] == 'failed'
    assert published[0]['message'] == 'drive fault'
    assert node._active_runtime_request == {}
    snapshot = node._executor.snapshot()
    assert snapshot['handles'][commands[0]['command_id']]['resultStatus'] == 'failed'
    assert snapshot['handles'][commands[1]['command_id']]['resultStatus'] == 'failed'



def test_dispatcher_command_exception_publishes_failed_feedback_with_context(monkeypatch) -> None:
    logger = _Logger()
    published: list[dict[str, str]] = []
    node = SimpleNamespace(
        runtime_active=True,
        _stats={'sent': 0, 'ack': 0, 'nack': 0, 'retry': 0, 'timeout': 0, 'done': 0, 'fault': 0, 'parser_error': 0, 'soft_done': 0},
        get_logger=lambda: logger,
        _publish_feedback=lambda payload: published.append(payload),
        _allocate_sequence=lambda: 9,
    )
    node._feedback_context = HardwareCommandDispatcherNode._feedback_context
    node._payload_feedback = lambda payload, **kwargs: HardwareCommandDispatcherNode._payload_feedback(node, payload, **kwargs)
    node._dispatch_failure_feedback = lambda payload, **kwargs: HardwareCommandDispatcherNode._dispatch_failure_feedback(node, payload, **kwargs)
    monkeypatch.setattr(dispatcher_module, 'build_frame', lambda command, sequence, payload: (_ for _ in ()).throw(RuntimeError('serial encode failed')))
    HardwareCommandDispatcherNode._on_command(node, _Msg(json.dumps({'kind': 'HOME', 'command_id': 'cmd-1', 'plan_id': 'plan-1', 'task_id': 'task-1', 'stage': 'go_home'})))
    assert logger.errors
    assert published
    assert published[0]['status'] == 'failed'
    assert published[0]['command_id'] == 'cmd-1'
    assert published[0]['message'] == 'serial encode failed'



def test_generated_runtime_contract_manifest_includes_lane_capabilities() -> None:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding='utf-8'))
    lanes = manifest['runtime']['laneCapabilities']
    assert lanes['sim_preview']['frameIngressMode'] == 'reserved_endpoint'
    assert lanes['sim_preview']['forwardHardwareCommands'] is False
    assert lanes['sim_authoritative']['hardwareExecutionMode'] == 'authoritative_simulation'
    assert lanes['sim_authoritative']['forwardHardwareCommands'] is True
