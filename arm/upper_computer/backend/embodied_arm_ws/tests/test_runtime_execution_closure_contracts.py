from __future__ import annotations

from pathlib import Path

from arm_backend_common.enums import HardwareCommand
from arm_hardware_bridge.feedback_tracker import PendingCommand
from arm_motion_executor.executor import MotionExecutor
from arm_motion_planner.planner import StagePlan

ROOT = Path(__file__).resolve().parents[1] / 'src'


def _build_plan() -> list[StagePlan]:
    return [
        StagePlan('move_to_pregrasp', 'connector', {'x': 0.1, 'y': 0.0, 'z': 0.1, 'yaw': 0.0, 'timeoutSec': 1.0}),
        StagePlan('go_home', 'connector', {'named_pose': 'home', 'timeoutSec': 1.0}),
    ]


def test_executor_command_stream_contains_stable_command_correlation_fields() -> None:
    executor = MotionExecutor()
    commands = executor.build_command_stream(_build_plan(), 'task-closure')
    assert commands
    for command in commands:
        assert command['command_id']
        assert command['plan_id']
        assert command['task_id'] == 'task-closure'
        assert command['stage']


def test_pending_command_summary_exposes_command_and_plan_identifiers() -> None:
    pending = PendingCommand(
        sequence=7,
        payload={'command_id': 'task-1:0:move', 'plan_id': 'plan-1', 'kind': 'EXEC_STAGE', 'stage': 'move', 'task_id': 'task-1'},
        command=HardwareCommand.EXEC_STAGE,
        sent_at=1.0,
    )
    summary = pending.to_summary(now=2.0)
    assert summary['sequence'] == 7
    assert summary['command_id'] == 'task-1:0:move'
    assert summary['plan_id'] == 'plan-1'
    assert summary['task_id'] == 'task-1'


def test_motion_executor_node_consumes_typed_state_and_fault_contracts() -> None:
    text = (ROOT / 'arm_motion_executor' / 'arm_motion_executor' / 'motion_executor_node.py').read_text(encoding='utf-8')
    assert 'create_subscription(HardwareState, TopicNames.HARDWARE_STATE' in text
    assert 'create_subscription(FaultReport, TopicNames.FAULT_REPORT' in text
    assert 'TopicNames.SYSTEM_FAULT' not in text


def test_dispatcher_feedback_builder_keeps_command_correlation_fields() -> None:
    text = (ROOT / 'arm_hardware_bridge' / 'arm_hardware_bridge' / 'hardware_command_dispatcher_node.py').read_text(encoding='utf-8')
    assert "'command_id'" in text
    assert "'plan_id'" in text
    assert "'request_id'" in text
    assert "'correlation_id'" in text
    assert "'task_run_id'" in text
