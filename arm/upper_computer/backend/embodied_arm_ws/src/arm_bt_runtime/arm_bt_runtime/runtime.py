from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import time
from typing import Callable


class NodeStatus(str, Enum):
    SUCCESS = 'SUCCESS'
    FAILURE = 'FAILURE'
    RUNNING = 'RUNNING'


@dataclass
class TickContext:
    """Shared tree context.

    Args:
        values: Mutable blackboard-like storage shared by all tree nodes.
        trace: Ordered node execution trace for debugging and tests.
        tick_count: Monotonic tick counter maintained by the runtime.
        status_by_node: Latest status observed for each labeled node.
        node_tick_durations_ms: Latest per-node tick duration in milliseconds.
        snapshots: Lightweight blackboard snapshots captured by the runtime.

    Returns:
        None.

    Raises:
        Does not raise directly.

    Boundary behavior:
        Snapshots are shallow copies so callers can inspect deterministic values
        without mutating the live blackboard structure used by running nodes.
    """

    values: dict[str, object] = field(default_factory=dict)
    trace: list[str] = field(default_factory=list)
    tick_count: int = 0
    status_by_node: dict[str, str] = field(default_factory=dict)
    node_tick_durations_ms: dict[str, float] = field(default_factory=dict)
    snapshots: list[dict[str, object]] = field(default_factory=list)

    def record(self, event: str) -> None:
        if event:
            self.trace.append(event)

    def record_status(self, label: str, status: NodeStatus, *, duration_ms: float | None = None) -> None:
        """Record one node status transition into trace and observability state.

        Args:
            label: Stable node label used for trace correlation.
            status: Node status produced by the current tick.
            duration_ms: Optional elapsed execution time for the node tick.

        Returns:
            None.

        Raises:
            Does not raise.
        """
        self.status_by_node[label] = status.value
        if duration_ms is not None:
            self.node_tick_durations_ms[label] = round(float(duration_ms), 3)
        self.record(f'{label}:{status.value}')

    def snapshot(self, *, note: str = '', keys: tuple[str, ...] | None = None) -> None:
        """Capture one shallow blackboard snapshot for traceability.

        Args:
            note: Optional snapshot label stored alongside the captured values.
            keys: Optional key subset. When omitted the full current blackboard is
                copied shallowly.

        Returns:
            None.

        Raises:
            Does not raise.
        """
        selected_keys = tuple(keys) if keys else tuple(self.values.keys())
        payload = {key: self.values.get(key) for key in selected_keys}
        self.snapshots.append({'tick': self.tick_count, 'note': note, 'values': payload})


class BehaviorNode:
    """Base behavior-tree node."""

    label: str

    def tick(self, context: TickContext) -> NodeStatus:
        raise NotImplementedError

    def reset(self, context: TickContext) -> None:
        del context


@dataclass
class SequenceNode(BehaviorNode):
    """Memory sequence node.

    The sequence remembers the child that returned ``RUNNING`` and resumes from
    that child on the next tick. If any child returns ``FAILURE`` the memory is
    reset so the next tick restarts from the first child.
    """

    children: list[BehaviorNode]
    label: str = 'sequence'
    _cursor: int = 0

    def tick(self, context: TickContext) -> NodeStatus:
        start = time.perf_counter()
        context.record(f'{self.label}:enter')
        while self._cursor < len(self.children):
            child = self.children[self._cursor]
            status = child.tick(context)
            context.record(f'{self.label}:{self._cursor}:{status.value}')
            if status is NodeStatus.SUCCESS:
                child.reset(context)
                self._cursor += 1
                continue
            if status is NodeStatus.FAILURE:
                self.reset(context)
                context.record_status(self.label, NodeStatus.FAILURE, duration_ms=(time.perf_counter() - start) * 1000.0)
                return NodeStatus.FAILURE
            context.record_status(self.label, NodeStatus.RUNNING, duration_ms=(time.perf_counter() - start) * 1000.0)
            return NodeStatus.RUNNING
        self.reset(context)
        context.record_status(self.label, NodeStatus.SUCCESS, duration_ms=(time.perf_counter() - start) * 1000.0)
        return NodeStatus.SUCCESS

    def reset(self, context: TickContext) -> None:
        for child in self.children:
            child.reset(context)
        self._cursor = 0


@dataclass
class FallbackNode(BehaviorNode):
    """Memory fallback node.

    The fallback remembers the child that returned ``RUNNING`` and resumes from
    it on the next tick. ``SUCCESS`` or exhaustion resets the child cursor.
    """

    children: list[BehaviorNode]
    label: str = 'fallback'
    _cursor: int = 0

    def tick(self, context: TickContext) -> NodeStatus:
        start = time.perf_counter()
        context.record(f'{self.label}:enter')
        while self._cursor < len(self.children):
            child = self.children[self._cursor]
            status = child.tick(context)
            context.record(f'{self.label}:{self._cursor}:{status.value}')
            if status is NodeStatus.FAILURE:
                child.reset(context)
                self._cursor += 1
                continue
            if status is NodeStatus.SUCCESS:
                self.reset(context)
                context.record_status(self.label, NodeStatus.SUCCESS, duration_ms=(time.perf_counter() - start) * 1000.0)
                return NodeStatus.SUCCESS
            context.record_status(self.label, NodeStatus.RUNNING, duration_ms=(time.perf_counter() - start) * 1000.0)
            return NodeStatus.RUNNING
        self.reset(context)
        context.record_status(self.label, NodeStatus.FAILURE, duration_ms=(time.perf_counter() - start) * 1000.0)
        return NodeStatus.FAILURE

    def reset(self, context: TickContext) -> None:
        for child in self.children:
            child.reset(context)
        self._cursor = 0


@dataclass
class ConditionNode(BehaviorNode):
    """Predicate node.

    Args:
        predicate: Callable returning ``True`` for success.
        label: Optional trace label.
    """

    predicate: Callable[[TickContext], bool]
    label: str = 'condition'

    def tick(self, context: TickContext) -> NodeStatus:
        start = time.perf_counter()
        result = NodeStatus.SUCCESS if self.predicate(context) else NodeStatus.FAILURE
        context.record_status(self.label, result, duration_ms=(time.perf_counter() - start) * 1000.0)
        return result


@dataclass
class ActionNode(BehaviorNode):
    """Action node with optional stateful lifecycle hooks.

    Args:
        action: One-shot action callback. Used when ``on_start``/``on_running``
            are not provided.
        label: Optional trace label.
        on_start: Optional callback executed once when the node starts.
        on_running: Optional callback executed on subsequent ticks while the node
            remains in ``RUNNING``.
        on_halt: Optional callback executed when the node is reset while running.

    Returns:
        None.

    Raises:
        ValueError: If neither ``action`` nor lifecycle callbacks are provided.

    Boundary behavior:
        If ``on_start`` is provided and returns ``RUNNING``, subsequent ticks use
        ``on_running`` when available, otherwise ``on_start`` is repeated.
    """

    action: Callable[[TickContext], NodeStatus] | None = None
    label: str = 'action'
    on_start: Callable[[TickContext], NodeStatus] | None = None
    on_running: Callable[[TickContext], NodeStatus] | None = None
    on_halt: Callable[[TickContext], None] | None = None
    _started: bool = False
    _last_status: NodeStatus = NodeStatus.SUCCESS

    def __post_init__(self) -> None:
        if self.action is None and self.on_start is None:
            raise ValueError('ActionNode requires action or on_start callback')

    def tick(self, context: TickContext) -> NodeStatus:
        start = time.perf_counter()
        callback: Callable[[TickContext], NodeStatus]
        if not self._started:
            self._started = True
            callback = self.on_start or self.action  # type: ignore[assignment]
        else:
            callback = self.on_running or self.action or self.on_start  # type: ignore[assignment]
        status = callback(context)
        self._last_status = status
        context.record_status(self.label, status, duration_ms=(time.perf_counter() - start) * 1000.0)
        if status is not NodeStatus.RUNNING:
            self._started = False
        return status

    def reset(self, context: TickContext) -> None:
        if self._started and self.on_halt is not None:
            self.on_halt(context)
            context.record(f'{self.label}:HALT')
        self._started = False
        self._last_status = NodeStatus.SUCCESS


@dataclass
class BehaviorTreeRuntime:
    """Behavior-tree runtime wrapper."""

    root: BehaviorNode

    def tick(self, context: TickContext | None = None) -> NodeStatus:
        """Tick the tree once.

        Args:
            context: Optional existing tick context. If omitted, a fresh context
                is created.

        Returns:
            NodeStatus: Root node status.

        Raises:
            Propagates exceptions from child node callbacks.

        Boundary behavior:
            The runtime records one shallow blackboard snapshot before each tick
            and resets the root after terminal statuses so the next admission
            starts from the entry node.
        """
        tick_context = context or TickContext()
        tick_context.tick_count += 1
        tick_context.snapshot(note='before_tick')
        status = self.root.tick(tick_context)
        tick_context.record_status('tree', status)
        if status is not NodeStatus.RUNNING:
            self.root.reset(tick_context)
        return status
