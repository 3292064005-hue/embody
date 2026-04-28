from __future__ import annotations

from arm_bt_runtime import ActionNode, ConditionNode, NodeStatus, TickContext


def readiness_condition(name: str):
    return ConditionNode(lambda context: bool((context.values.get('checks') or {}).get(name, False)))


def _resolve_status(raw: object, *, fallback: NodeStatus) -> NodeStatus:
    if raw is None:
        return fallback
    if isinstance(raw, NodeStatus):
        return raw
    normalized = str(raw or '').strip().upper()
    if not normalized:
        return fallback
    try:
        return NodeStatus[normalized]
    except KeyError as exc:  # pragma: no cover - deterministic guard
        raise RuntimeError(f'unsupported behavior-tree event status: {raw!r}') from exc


def status_action(name: str, status: NodeStatus = NodeStatus.SUCCESS, pending_status: NodeStatus = NodeStatus.RUNNING):
    """Build one action node whose observable status is driven by runtime event state.

    Args:
        name: Stable event name recorded into the tick trace and event ledger.
        status: Fallback terminal status when no runtime-specific event state is supplied.
        pending_status: Status used before the runtime marks the named event as terminal.

    Returns:
        ActionNode: Stateful action node compatible with the task-runtime tree.

    Raises:
        RuntimeError: If the runtime provides an unsupported named status override.

    Boundary behavior:
        The node appends its event name to ``context.values['events']`` on every tick so
        callers can inspect repeated progress. Runtime-specific statuses are read from
        ``context.values['event_statuses'][name]``. Missing entries do not fail closed;
        they return ``pending_status`` so the tree can remain RUNNING until the runtime
        actually dispatches the corresponding stage.
    """
    def _action(context: TickContext) -> NodeStatus:
        events = context.values.setdefault('events', [])
        if isinstance(events, list):
            events.append(name)
        event_statuses = context.values.get('event_statuses', {})
        raw = event_statuses.get(name) if isinstance(event_statuses, dict) else None
        if raw is None:
            return pending_status
        return _resolve_status(raw, fallback=status)

    return ActionNode(_action, label=name)
