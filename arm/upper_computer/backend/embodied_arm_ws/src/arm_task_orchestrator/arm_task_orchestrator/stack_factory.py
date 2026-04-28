from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from arm_backend_common.data_models import TaskProfile
from arm_task_orchestrator.application_service import TaskApplicationService
from arm_task_orchestrator.execution_adapter import ExecutionAdapter
from arm_task_orchestrator.fault_manager import FaultManager
from arm_task_orchestrator.orchestrator import TaskOrchestrator
from arm_task_orchestrator.runtime import RuntimeHooks, TaskRuntimeEngine, TaskRuntimeState
from arm_task_orchestrator.state_machine import SystemStateMachine
from arm_task_orchestrator.verification import VerificationManager
from arm_perception import VisionTargetTracker
from arm_bt_runtime import BehaviorNode, BehaviorTreeRuntime, FallbackNode, NodeStatus, SequenceNode
from arm_bt_nodes import readiness_condition, status_action

DEFAULT_TASK_TREE_PATH = Path(__file__).resolve().parents[1] / 'arm_bt_trees' / 'pick_place.yaml'


def build_target_tracker(task_profile: TaskProfile, *, stable_seen_count: int) -> VisionTargetTracker:
    """Create the runtime vision tracker from task-profile thresholds.

    Args:
        task_profile: Task profile containing stale-target timing constraints.
        stable_seen_count: Minimum stable detections required before a target is treated as valid.

    Returns:
        A configured `VisionTargetTracker` instance.

    Raises:
        ValueError: Propagated if downstream tracker construction rejects invalid numeric values.

    Boundary behavior:
        Stable detection count is clamped to at least one observation.
    """
    return VisionTargetTracker(
        stale_after_sec=task_profile.stale_target_sec,
        min_seen_count=max(1, int(stable_seen_count)),
    )


def build_application_service(
    task_profile: TaskProfile,
    execution_adapter: ExecutionAdapter,
    verification: VerificationManager,
    fault_manager: FaultManager,
) -> tuple[TaskOrchestrator, TaskApplicationService]:
    """Build the orchestrator/application pair used by the task runtime.

    Args:
        task_profile: Active task profile driving orchestration policy.
        execution_adapter: Adapter that forwards high-level task intents to execution transport.
        verification: Verification manager for calibration and precondition checks.
        fault_manager: Fault manager coordinating latching and recovery policies.

    Returns:
        A `(TaskOrchestrator, TaskApplicationService)` tuple wired to the supplied dependencies.

    Raises:
        ValueError: Propagated if downstream constructors reject invalid task-profile data.

    Boundary behavior:
        The application service is created with a deferred runtime engine reference that is bound later.
    """
    orchestrator = TaskOrchestrator(task_profile)
    application = TaskApplicationService(
        orchestrator,
        None,
        execution_adapter,
        verification,
        fault_manager,
        task_profile,
    )
    return orchestrator, application


def build_runtime_engine(
    *,
    state_machine: SystemStateMachine,
    application: TaskApplicationService,
    execution_adapter: ExecutionAdapter,
    fault_manager: FaultManager,
    tracker: VisionTargetTracker,
    state: TaskRuntimeState,
    hooks: RuntimeHooks,
    behavior_tree: BehaviorTreeRuntime | None = None,
) -> TaskRuntimeEngine:
    """Assemble the runtime engine that coordinates task-state execution.

    Args:
        state_machine: State machine governing operator-visible task transitions.
        application: Application service handling task orchestration rules.
        execution_adapter: Adapter bridging runtime decisions into motion execution calls.
        fault_manager: Fault manager tracking latches and recovery transitions.
        tracker: Vision tracker used to stabilize perception targets.
        state: Mutable runtime state snapshot.
        hooks: Runtime hooks for telemetry and gateway-facing side effects.

    Returns:
        A fully configured `TaskRuntimeEngine`.

    Raises:
        ValueError: Propagated if engine construction receives invalid dependencies.

    Boundary behavior:
        No ROS side effects are triggered during construction; wiring is purely in-memory.
    """
    active_behavior_tree = behavior_tree or build_task_behavior_tree()
    return TaskRuntimeEngine(
        state_machine=state_machine,
        application=application,
        execution_adapter=execution_adapter,
        fault_manager=fault_manager,
        tracker=tracker,
        state=state,
        hooks=hooks,
        behavior_tree=active_behavior_tree,
    )


def _load_tree_spec(path: Path) -> dict[str, Any]:
    """Load one task-tree specification file.

    Args:
        path: YAML tree-spec path.

    Returns:
        Parsed tree specification mapping.

    Raises:
        RuntimeError: If the YAML is missing, malformed, or not a mapping.

    Boundary behavior:
        Invalid specs fail closed; no fallback hard-coded tree is fabricated.
    """
    try:
        payload = yaml.safe_load(path.read_text(encoding='utf-8')) or {}
    except Exception as exc:  # pragma: no cover - exercised through callers/tests
        raise RuntimeError(f'failed to load task behavior-tree spec {path}: {exc}') from exc
    if not isinstance(payload, dict):
        raise RuntimeError(f'task behavior-tree spec must be a mapping: {path}')
    return payload


def _action_status(name: str) -> NodeStatus:
    normalized = str(name or 'SUCCESS').strip().upper()
    try:
        return NodeStatus[normalized]
    except KeyError as exc:  # pragma: no cover - deterministic validation path
        raise RuntimeError(f'unsupported task action status {name!r}') from exc


def _build_node_from_spec(node_id: str, nodes: dict[str, Any], *, stack: tuple[str, ...] = ()) -> BehaviorNode:
    if node_id in stack:
        cycle = ' -> '.join((*stack, node_id))
        raise RuntimeError(f'task behavior-tree spec contains a cycle: {cycle}')
    raw = nodes.get(node_id)
    if not isinstance(raw, dict):
        raise RuntimeError(f'task behavior-tree node {node_id!r} must be a mapping')
    node_type = str(raw.get('type', '') or '').strip().lower()
    next_stack = (*stack, node_id)
    if node_type == 'sequence':
        children = raw.get('children', [])
        if not isinstance(children, list) or not children:
            raise RuntimeError(f'sequence node {node_id!r} must declare a non-empty children list')
        return SequenceNode(children=[_build_node_from_spec(str(child), nodes, stack=next_stack) for child in children], label=node_id)
    if node_type == 'fallback':
        children = raw.get('children', [])
        if not isinstance(children, list) or not children:
            raise RuntimeError(f'fallback node {node_id!r} must declare a non-empty children list')
        return FallbackNode(children=[_build_node_from_spec(str(child), nodes, stack=next_stack) for child in children], label=node_id)
    if node_type == 'condition':
        check_name = str(raw.get('check', '') or '').strip()
        if not check_name:
            raise RuntimeError(f'condition node {node_id!r} missing required check field')
        node = readiness_condition(check_name)
        node.label = node_id
        return node
    if node_type == 'action':
        event_name = str(raw.get('event', '') or '').strip()
        if not event_name:
            raise RuntimeError(f'action node {node_id!r} missing required event field')
        node = status_action(event_name, status=_action_status(str(raw.get('status', 'SUCCESS') or 'SUCCESS')))
        node.label = node_id
        return node
    raise RuntimeError(f'unsupported task behavior-tree node type for {node_id!r}: {node_type or "<empty>"}')


def build_task_behavior_tree(tree_path: Path | None = None) -> BehaviorTreeRuntime:
    """Build the default task-orchestration behavior tree from a declarative spec.

    Args:
        tree_path: Optional override path for the YAML behavior-tree specification.

    Returns:
        BehaviorTreeRuntime wired from the validated YAML spec.

    Raises:
        RuntimeError: If the tree specification is missing required nodes,
            contains cycles, or references unsupported node contracts.

    Boundary behavior:
        The function fails closed instead of fabricating a fallback tree. This
        keeps the task-graph contract explicit and reviewable.
    """
    spec_path = tree_path or DEFAULT_TASK_TREE_PATH
    spec = _load_tree_spec(spec_path)
    root_id = str(spec.get('root', '') or '').strip()
    nodes = spec.get('nodes', {}) if isinstance(spec.get('nodes'), dict) else {}
    if not root_id:
        raise RuntimeError(f'task behavior-tree spec missing root node: {spec_path}')
    if root_id not in nodes:
        raise RuntimeError(f'task behavior-tree root node {root_id!r} missing from spec: {spec_path}')
    return BehaviorTreeRuntime(root=_build_node_from_spec(root_id, nodes))
