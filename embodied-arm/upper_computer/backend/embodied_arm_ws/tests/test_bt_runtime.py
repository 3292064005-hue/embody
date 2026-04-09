from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1] / 'src'
sys.path.insert(0, str(ROOT / 'arm_bt_runtime'))
sys.path.insert(0, str(ROOT / 'arm_bt_nodes'))
sys.path.insert(0, str(ROOT / 'arm_task_orchestrator'))

from arm_bt_runtime import NodeStatus, TickContext
from arm_task_orchestrator.stack_factory import build_task_behavior_tree


def test_behavior_tree_emits_plan_and_execution_events_when_ready() -> None:
    tree = build_task_behavior_tree()
    context = TickContext(values={'checks': {'motion_planner': True}, 'events': []})
    status = tree.tick(context)
    assert status is NodeStatus.SUCCESS
    assert context.values['events'] == ['plan_requested', 'execution_requested']


def test_behavior_tree_blocks_when_planner_not_ready() -> None:
    tree = build_task_behavior_tree()
    context = TickContext(values={'checks': {'motion_planner': False}, 'events': []})
    status = tree.tick(context)
    assert status is NodeStatus.FAILURE
    assert context.values['events'] == []
