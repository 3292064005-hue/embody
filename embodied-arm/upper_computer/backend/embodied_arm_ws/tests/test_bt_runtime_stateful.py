from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1] / 'src'
sys.path.insert(0, str(ROOT / 'arm_bt_runtime'))

from arm_bt_runtime import ActionNode, BehaviorTreeRuntime, ConditionNode, NodeStatus, SequenceNode, TickContext


def test_sequence_node_resumes_running_child_and_records_trace() -> None:
    context = TickContext(values={'ready': True})
    ticks = {'count': 0}

    def _running_action(_context: TickContext) -> NodeStatus:
        ticks['count'] += 1
        return NodeStatus.RUNNING if ticks['count'] == 1 else NodeStatus.SUCCESS

    tree = BehaviorTreeRuntime(
        SequenceNode(
            [
                ConditionNode(lambda ctx: bool(ctx.values.get('ready')), label='ready-check'),
                ActionNode(action=_running_action, label='exec-step'),
            ],
            label='main-sequence',
        )
    )

    assert tree.tick(context) is NodeStatus.RUNNING
    assert tree.tick(context) is NodeStatus.SUCCESS
    assert 'main-sequence:0:SUCCESS' in context.trace
    assert 'exec-step:RUNNING' in context.trace
    assert 'exec-step:SUCCESS' in context.trace
