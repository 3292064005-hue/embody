from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping, Protocol

import yaml

from arm_backend_common.data_models import TargetSnapshot

TASK_CAPABILITY_MANIFEST_PATH = Path(__file__).resolve().parents[2] / 'arm_bringup' / 'config' / 'task_capability_manifest.yaml'


@dataclass(frozen=True)
class StageIOContract:
    """Authoritative one-stage runtime contract.

    Attributes:
        stage: Canonical runtime stage identifier.
        inputs: Required upstream inputs that must already be available before the
            stage transition hook is allowed to consume the transition.
        outputs: State or transport artifacts the stage produces when accepted.
        terminal_statuses: Authoritative terminal statuses observed at this stage.
        recovery_entrypoint: Stage name used when a retryable failure routes the
            task back into the runtime loop.
    """

    stage: str
    inputs: tuple[str, ...] = ()
    outputs: tuple[str, ...] = ()
    terminal_statuses: tuple[str, ...] = ()
    recovery_entrypoint: str = ''


class TargetSelectionPlugin(Protocol):
    """Resolve the next candidate target for one task-family runtime."""

    def select_target(self, engine: Any) -> TargetSnapshot | None:
        """Select the next runtime target or return ``None`` when none qualify."""


class StagePolicyPlugin(Protocol):
    """Allow one task family to consume stage transitions without forking runtime."""

    def on_plan_accepted(self, engine: Any, payload: Mapping[str, Any], *, contract: StageIOContract) -> bool:
        """Handle one accepted plan result.

        Returns ``True`` when the plugin fully consumes the transition.
        """

    def on_execution_success(self, engine: Any, payload: Mapping[str, Any], *, contract: StageIOContract) -> bool:
        """Handle one successful execution result before default verify entry."""

    def on_verify_success(self, engine: Any, message: str, *, perception_blocked_after_sec: float, contract: StageIOContract) -> bool:
        """Handle one successful verification result before default completion."""


class RecoveryPolicyPlugin(Protocol):
    """Route retryable runtime faults for one task family."""

    def on_retryable_fault(self, engine: Any, *, message: str, perception_blocked_after_sec: float, contract: StageIOContract) -> bool:
        """Handle one retryable runtime fault.

        Returns ``True`` when the plugin consumes the retry path and keeps the
        runtime active.
        """


class TaskFamilyRuntimePlugin(Protocol):
    """Composable runtime plugin assembled from selection / stage / recovery contracts."""

    key: str
    target_selector: TargetSelectionPlugin
    stage_policy: StagePolicyPlugin
    recovery_policy: RecoveryPolicyPlugin
    stage_contracts: Mapping[str, StageIOContract]

    def stage_contract(self, stage: str) -> StageIOContract:
        """Return the authoritative stage contract for ``stage``."""

    # Compatibility delegates kept so existing runtime/tests keep a stable call surface.
    def select_target(self, engine: Any) -> TargetSnapshot | None:
        ...

    def on_plan_accepted(self, engine: Any, payload: Mapping[str, Any]) -> bool:
        ...

    def on_execution_success(self, engine: Any, payload: Mapping[str, Any]) -> bool:
        ...

    def on_verify_success(self, engine: Any, message: str, *, perception_blocked_after_sec: float) -> bool:
        ...

    def on_retryable_fault(self, engine: Any, *, message: str, perception_blocked_after_sec: float) -> bool:
        ...


@lru_cache(maxsize=1)
def _task_template_records() -> list[dict[str, Any]]:
    try:
        payload = yaml.safe_load(TASK_CAPABILITY_MANIFEST_PATH.read_text(encoding='utf-8')) or {}
    except Exception:
        return []
    templates = payload.get('templates', []) if isinstance(payload, dict) else []
    return [dict(item) for item in templates if isinstance(item, dict)]


@lru_cache(maxsize=1)
def _backend_task_plugin_map() -> dict[str, str]:
    templates = _task_template_records()
    mapping: dict[str, str] = {}
    for item in templates:
        if not isinstance(item, dict):
            continue
        backend_task_type = str(item.get('backend_task_type', '') or '').strip().upper()
        plugin_key = str(item.get('plugin_key', item.get('sequence_mode', 'single_target')) or 'single_target').strip() or 'single_target'
        if backend_task_type:
            mapping[backend_task_type] = plugin_key
    return mapping or {
        'PICK_AND_PLACE': 'single_target',
        'PICK_BY_COLOR': 'selector_routed',
        'PICK_BY_QR': 'selector_routed',
        'CLEAR_TABLE': 'continuous',
    }


@dataclass(frozen=True)
class SingleTargetSelector:
    def select_target(self, engine: Any) -> TargetSnapshot | None:
        current = engine.state.current
        if current is None:
            return None
        return engine.tracker.select(current.target_selector, exclude_keys=current.completed_target_ids)


@dataclass(frozen=True)
class SelectorRoutedTargetSelector(SingleTargetSelector):
    """Selector-routed tasks reuse the runtime's authoritative tracker selection."""


@dataclass(frozen=True)
class ContinuousTargetSelector:
    def select_target(self, engine: Any) -> TargetSnapshot | None:
        current = engine.state.current
        if current is None:
            return None
        selector = current.target_selector or ''
        return engine.tracker.select(selector, exclude_keys=current.completed_target_ids)


@dataclass(frozen=True)
class DefaultStagePolicy:
    def on_plan_accepted(self, engine: Any, payload: Mapping[str, Any], *, contract: StageIOContract) -> bool:
        del engine, payload, contract
        return False

    def on_execution_success(self, engine: Any, payload: Mapping[str, Any], *, contract: StageIOContract) -> bool:
        del engine, payload, contract
        return False

    def on_verify_success(self, engine: Any, message: str, *, perception_blocked_after_sec: float, contract: StageIOContract) -> bool:
        del engine, message, perception_blocked_after_sec, contract
        return False


@dataclass(frozen=True)
class ContinuousStagePolicy(DefaultStagePolicy):
    def on_verify_success(self, engine: Any, message: str, *, perception_blocked_after_sec: float, contract: StageIOContract) -> bool:
        del contract
        current = engine.state.current
        if current is None:
            return False
        completed_limit = max(1, int(engine.state.task_profile.clear_table_max_items or 1))
        current.complete_count += 1
        if current.complete_count >= completed_limit:
            return False
        return bool(
            engine.continue_with_next_target(
                message,
                perception_blocked_after_sec=perception_blocked_after_sec,
                reason_suffix='continuing to next target',
                mark_selected_completed=True,
            )
        )


@dataclass(frozen=True)
class DefaultRecoveryPolicy:
    def on_retryable_fault(self, engine: Any, *, message: str, perception_blocked_after_sec: float, contract: StageIOContract) -> bool:
        del engine, message, perception_blocked_after_sec, contract
        return False


@dataclass(frozen=True)
class ContinuousRecoveryPolicy(DefaultRecoveryPolicy):
    def on_retryable_fault(self, engine: Any, *, message: str, perception_blocked_after_sec: float, contract: StageIOContract) -> bool:
        del contract
        current = engine.state.current
        if current is not None and getattr(current, 'current_retry', 0) > 0:
            current.current_retry -= 1
        return bool(
            engine.continue_with_next_target(
                message,
                perception_blocked_after_sec=perception_blocked_after_sec,
                reason_suffix='retryable fault routed to next target',
                mark_selected_completed=True,
            )
        )


DEFAULT_STAGE_CONTRACTS: Mapping[str, StageIOContract] = {
    'planning': StageIOContract(
        stage='planning',
        inputs=('selected_target', 'planning_request'),
        outputs=('plan_result', 'stage_plan'),
        terminal_statuses=('accepted', 'rejected', 'failed'),
        recovery_entrypoint='perception',
    ),
    'execution': StageIOContract(
        stage='execution',
        inputs=('stage_plan', 'execution_request'),
        outputs=('execution_status',),
        terminal_statuses=('done', 'succeeded', 'timeout', 'canceled', 'failed', 'fault'),
        recovery_entrypoint='planning',
    ),
    'verification': StageIOContract(
        stage='verification',
        inputs=('hardware_snapshot', 'target_tracker'),
        outputs=('verification_decision',),
        terminal_statuses=('success', 'failed', 'retryable_fault'),
        recovery_entrypoint='perception',
    ),
}


@dataclass(frozen=True)
class ComposedTaskFamilyRuntimePlugin:
    key: str
    target_selector: TargetSelectionPlugin
    stage_policy: StagePolicyPlugin = field(default_factory=DefaultStagePolicy)
    recovery_policy: RecoveryPolicyPlugin = field(default_factory=DefaultRecoveryPolicy)
    stage_contracts: Mapping[str, StageIOContract] = field(default_factory=lambda: DEFAULT_STAGE_CONTRACTS)

    def stage_contract(self, stage: str) -> StageIOContract:
        normalized = str(stage or '').strip().lower()
        return self.stage_contracts.get(normalized, StageIOContract(stage=normalized or 'unknown'))

    def select_target(self, engine: Any) -> TargetSnapshot | None:
        return self.target_selector.select_target(engine)

    def on_plan_accepted(self, engine: Any, payload: Mapping[str, Any]) -> bool:
        return self.stage_policy.on_plan_accepted(engine, payload, contract=self.stage_contract('planning'))

    def on_execution_success(self, engine: Any, payload: Mapping[str, Any]) -> bool:
        return self.stage_policy.on_execution_success(engine, payload, contract=self.stage_contract('execution'))

    def on_verify_success(self, engine: Any, message: str, *, perception_blocked_after_sec: float) -> bool:
        return self.stage_policy.on_verify_success(
            engine,
            message,
            perception_blocked_after_sec=perception_blocked_after_sec,
            contract=self.stage_contract('verification'),
        )

    def on_retryable_fault(self, engine: Any, *, message: str, perception_blocked_after_sec: float) -> bool:
        return self.recovery_policy.on_retryable_fault(
            engine,
            message=message,
            perception_blocked_after_sec=perception_blocked_after_sec,
            contract=self.stage_contract('verification'),
        )


PLUGIN_REGISTRY: dict[str, TaskFamilyRuntimePlugin] = {
    'single_target': ComposedTaskFamilyRuntimePlugin(key='single_target', target_selector=SingleTargetSelector()),
    'selector_routed': ComposedTaskFamilyRuntimePlugin(key='selector_routed', target_selector=SelectorRoutedTargetSelector()),
    'continuous': ComposedTaskFamilyRuntimePlugin(
        key='continuous',
        target_selector=ContinuousTargetSelector(),
        stage_policy=ContinuousStagePolicy(),
        recovery_policy=ContinuousRecoveryPolicy(),
    ),
}


def resolve_task_runtime_plugin(task_type: str, *, metadata: dict[str, Any] | None = None) -> TaskFamilyRuntimePlugin:
    """Resolve the authoritative task-runtime plugin for one backend task type.

    Args:
        task_type: Backend task type stored in TaskRequest/TaskContext.
        metadata: Optional task metadata. ``pluginKey`` takes precedence when supplied.

    Returns:
        TaskFamilyRuntimePlugin: Registered runtime plugin. Unknown values fail closed
        to ``single_target``.

    Raises:
        Does not raise. Missing manifest data degrades to the default registry.
    """
    meta = metadata if isinstance(metadata, dict) else {}
    explicit = str(meta.get('pluginKey', '') or '').strip()
    if explicit and explicit in PLUGIN_REGISTRY:
        return PLUGIN_REGISTRY[explicit]
    mapping = _backend_task_plugin_map()
    key = mapping.get(str(task_type or '').strip().upper(), 'single_target')
    return PLUGIN_REGISTRY.get(key, PLUGIN_REGISTRY['single_target'])


_TASK_TYPE_ALIASES = {
    'pick_place': {'pick_place', 'pick_and_place', 'PICK_AND_PLACE'},
    'sort_by_color': {'sort_by_color', 'pick_by_color', 'PICK_BY_COLOR'},
    'sort_by_qr': {'sort_by_qr', 'pick_by_qr', 'PICK_BY_QR'},
    'clear_table': {'clear_table', 'CLEAR_TABLE'},
}


def resolve_task_graph_contract(task_type: str, *, target_selector: str = '', metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    """Resolve task-graph metadata for one task request.

    Args:
        task_type: Frontend or backend task type.
        target_selector: Optional selector/category used to disambiguate templates.
        metadata: Existing request metadata. Explicit graph/plugin keys take precedence.

    Returns:
        dict[str, Any]: Normalized graph metadata carrying graphKey, taskGraph, pluginKey and sequenceMode.

    Boundary behavior:
        Unknown task types fail closed to an empty mapping instead of fabricating a graph.
    """
    meta = dict(metadata or {})
    explicit_graph = str(meta.get('graphKey', '') or '').strip()
    explicit_graph_spec = meta.get('taskGraph') if isinstance(meta.get('taskGraph'), dict) else None
    explicit_plugin = str(meta.get('pluginKey', '') or '').strip()
    explicit_sequence = str(meta.get('sequenceMode', '') or '').strip()
    if explicit_graph and explicit_graph_spec:
        return {
            'graphKey': explicit_graph,
            'taskGraph': dict(explicit_graph_spec),
            'pluginKey': explicit_plugin or str(explicit_graph_spec.get('pluginKey', '') or ''),
            'sequenceMode': explicit_sequence or str(explicit_graph_spec.get('sequenceMode', '') or ''),
        }
    selector = str(target_selector or '').strip().lower()
    type_norm = str(task_type or '').strip()
    candidates = _TASK_TYPE_ALIASES.get(type_norm, {type_norm, type_norm.upper()})
    candidate_upper = {value.upper() for value in candidates}
    for item in _task_template_records():
        frontend_type = str(item.get('frontend_task_type', '') or '').strip()
        backend_type = str(item.get('backend_task_type', '') or '').strip()
        if frontend_type not in candidates and backend_type not in candidates and backend_type.upper() not in candidate_upper:
            continue
        allowed = [str(value).strip().lower() for value in item.get('allowed_target_categories', []) if str(value).strip()]
        default_selector = str(item.get('default_target_category', '') or '').strip().lower()
        if allowed and selector and selector not in allowed:
            continue
        if selector and not allowed and default_selector and selector != default_selector:
            continue
        graph = item.get('task_graph') if isinstance(item.get('task_graph'), dict) else item.get('taskGraph') if isinstance(item.get('taskGraph'), dict) else {}
        graph_key = str(item.get('graph_key', item.get('graphKey', item.get('id', ''))) or '').strip()
        plugin_key = str(item.get('plugin_key', item.get('pluginKey', item.get('sequence_mode', 'single_target'))) or 'single_target').strip()
        sequence_mode = str(item.get('sequence_mode', item.get('sequenceMode', plugin_key)) or plugin_key).strip()
        if graph_key and graph:
            return {
                'graphKey': graph_key,
                'taskGraph': dict(graph),
                'pluginKey': plugin_key,
                'sequenceMode': sequence_mode,
            }
    return {}


# Compatibility aliases retained for tests and non-active diagnostic helpers.
class ContinuousPlugin(ComposedTaskFamilyRuntimePlugin):
    def __init__(self) -> None:
        super().__init__(
            key='continuous',
            target_selector=ContinuousTargetSelector(),
            stage_policy=ContinuousStagePolicy(),
            recovery_policy=ContinuousRecoveryPolicy(),
        )


class SingleTargetPlugin(ComposedTaskFamilyRuntimePlugin):
    def __init__(self) -> None:
        super().__init__(key='single_target', target_selector=SingleTargetSelector())


class SelectorRoutedPlugin(ComposedTaskFamilyRuntimePlugin):
    def __init__(self) -> None:
        super().__init__(key='selector_routed', target_selector=SelectorRoutedTargetSelector())
