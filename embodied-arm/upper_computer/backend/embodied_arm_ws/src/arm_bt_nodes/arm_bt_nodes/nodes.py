from __future__ import annotations

from arm_bt_runtime import ActionNode, ConditionNode, NodeStatus, TickContext


def readiness_condition(name: str):
    return ConditionNode(lambda context: bool((context.values.get('checks') or {}).get(name, False)))


def status_action(name: str, status: NodeStatus = NodeStatus.SUCCESS):
    def _action(context: TickContext) -> NodeStatus:
        events = context.values.setdefault('events', [])
        if isinstance(events, list):
            events.append(name)
        return status
    return ActionNode(_action)
