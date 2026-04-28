from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1] / 'src'
sys.path.insert(0, str(ROOT / 'arm_bt_runtime'))
sys.path.insert(0, str(ROOT / 'arm_bt_nodes'))
sys.path.insert(0, str(ROOT / 'arm_task_orchestrator'))

from arm_bt_runtime import NodeStatus, TickContext
from arm_task_orchestrator.stack_factory import build_task_behavior_tree


def test_behavior_tree_tracks_perception_plan_execution_and_verification_flow() -> None:
    tree = build_task_behavior_tree()
    context = TickContext(
        values={
            'checks': {
                'motion_planner': True,
                'auto_retry_enabled': True,
                'automatic_retry_budget_available': True,
                'retry_pending': False,
                'recovery_pending': False,
                'manual_recovery_preferred': False,
                'retry_budget_available': True,
                'plan_dispatch_ready': True,
                'execution_dispatch_ready': True,
                'verification_dispatch_ready': True,
            },
            'events': [],
            'event_statuses': {},
        }
    )
    assert tree.tick(context) is NodeStatus.RUNNING
    assert context.values['events'] == ['perception_requested']

    context.values['event_statuses']['perception_requested'] = 'SUCCESS'
    assert tree.tick(context) is NodeStatus.RUNNING
    assert context.values['events'][-2:] == ['perception_requested', 'plan_requested']

    context.values['event_statuses']['plan_requested'] = 'SUCCESS'
    assert tree.tick(context) is NodeStatus.RUNNING
    assert context.values['events'][-2:] == ['plan_requested', 'execution_requested']

    context.values['event_statuses']['execution_requested'] = 'SUCCESS'
    assert tree.tick(context) is NodeStatus.RUNNING
    assert context.values['events'][-2:] == ['execution_requested', 'verification_completed']

    context.values['event_statuses']['verification_completed'] = 'SUCCESS'
    assert tree.tick(context) is NodeStatus.SUCCESS
    assert context.status_by_node['dispatch_perception'] == 'SUCCESS'
    assert context.status_by_node['dispatch_plan'] == 'SUCCESS'
    assert context.status_by_node['dispatch_execute'] == 'SUCCESS'
    assert context.status_by_node['dispatch_verify'] == 'SUCCESS'


def test_behavior_tree_routes_retry_branch_before_active_flow() -> None:
    tree = build_task_behavior_tree()
    context = TickContext(
        values={
            'checks': {
                'motion_planner': True,
                'auto_retry_enabled': True,
                'automatic_retry_budget_available': True,
                'retry_pending': True,
                'recovery_pending': False,
                'manual_recovery_preferred': False,
                'retry_budget_available': True,
                'plan_dispatch_ready': True,
                'execution_dispatch_ready': True,
                'verification_dispatch_ready': True,
            },
            'events': [],
            'event_statuses': {'retry_requested': 'SUCCESS'},
        }
    )
    status = tree.tick(context)
    assert status is NodeStatus.SUCCESS
    assert context.values['events'] == ['retry_requested']
    assert context.status_by_node['retry_flow'] == 'SUCCESS'


def test_behavior_tree_blocks_active_flow_when_planner_not_ready() -> None:
    tree = build_task_behavior_tree()
    context = TickContext(
        values={
            'checks': {
                'motion_planner': False,
                'auto_retry_enabled': False,
                'automatic_retry_budget_available': False,
                'retry_pending': False,
                'recovery_pending': False,
                'manual_recovery_preferred': False,
                'retry_budget_available': False,
                'plan_dispatch_ready': True,
                'execution_dispatch_ready': True,
                'verification_dispatch_ready': True,
            },
            'events': [],
            'event_statuses': {'perception_requested': 'SUCCESS'},
        }
    )
    status = tree.tick(context)
    assert status is NodeStatus.FAILURE
    assert context.values['events'] == ['perception_requested']


def test_behavior_tree_routes_manual_recovery_policy_before_active_flow() -> None:
    tree = build_task_behavior_tree()
    context = TickContext(
        values={
            'checks': {
                'motion_planner': True,
                'auto_retry_enabled': False,
                'automatic_retry_budget_available': False,
                'retry_pending': True,
                'recovery_pending': False,
                'manual_recovery_preferred': True,
                'retry_budget_available': True,
                'plan_dispatch_ready': True,
                'execution_dispatch_ready': True,
                'verification_dispatch_ready': True,
            },
            'events': [],
            'event_statuses': {'recovery_requested': 'SUCCESS'},
        }
    )
    status = tree.tick(context)
    assert status is NodeStatus.SUCCESS
    assert context.values['events'] == ['recovery_requested']
    assert context.status_by_node['recovery_flow'] == 'SUCCESS'


def test_behavior_tree_blocks_verification_dispatch_until_gate_ready() -> None:
    tree = build_task_behavior_tree()
    context = TickContext(
        values={
            'checks': {
                'motion_planner': True,
                'auto_retry_enabled': False,
                'automatic_retry_budget_available': False,
                'retry_pending': False,
                'recovery_pending': False,
                'manual_recovery_preferred': False,
                'retry_budget_available': True,
                'plan_dispatch_ready': True,
                'execution_dispatch_ready': True,
                'verification_dispatch_ready': False,
            },
            'events': [],
            'event_statuses': {
                'perception_requested': 'SUCCESS',
                'plan_requested': 'SUCCESS',
                'execution_requested': 'SUCCESS',
            },
        }
    )
    status = tree.tick(context)
    assert status is NodeStatus.FAILURE
    assert context.values['events'] == ['perception_requested', 'plan_requested', 'execution_requested']
