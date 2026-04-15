from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Protocol

import yaml

from arm_backend_common.data_models import TargetSnapshot

TASK_CAPABILITY_MANIFEST_PATH = Path(__file__).resolve().parents[2] / 'arm_bringup' / 'config' / 'task_capability_manifest.yaml'


class TaskRuntimePlugin(Protocol):
    """Composable task-runtime stage hook contract.

    The runtime still executes the same authoritative split-stack stages, but
    task-specific branching is routed through this contract so new task modes do
    not have to fork the entire runtime loop.
    """

    key: str

    def select_target(self, engine: Any) -> TargetSnapshot | None:
        """Select the next target for the active task context."""

    def on_verify_success(self, engine: Any, message: str, *, perception_blocked_after_sec: float) -> bool:
        """Handle a successful verification result.

        Returns ``True`` when the plugin consumes the success path and keeps the
        runtime active; returns ``False`` to let the default completion logic run.
        """


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
class SingleTargetPlugin:
    key: str = 'single_target'

    def select_target(self, engine: Any) -> TargetSnapshot | None:
        current = engine.state.current
        if current is None:
            return None
        return engine.tracker.select(current.target_selector, exclude_keys=current.completed_target_ids)

    def on_verify_success(self, engine: Any, message: str, *, perception_blocked_after_sec: float) -> bool:
        del engine, message, perception_blocked_after_sec
        return False


@dataclass(frozen=True)
class SelectorRoutedPlugin(SingleTargetPlugin):
    key: str = 'selector_routed'


@dataclass(frozen=True)
class ContinuousPlugin:
    key: str = 'continuous'

    def select_target(self, engine: Any) -> TargetSnapshot | None:
        current = engine.state.current
        if current is None:
            return None
        selector = current.target_selector or ''
        return engine.tracker.select(selector, exclude_keys=current.completed_target_ids)

    def on_verify_success(self, engine: Any, message: str, *, perception_blocked_after_sec: float) -> bool:
        current = engine.state.current
        if current is None:
            return False
        completed_limit = max(1, int(engine.state.task_profile.clear_table_max_items or 1))
        selected = current.selected_target
        if selected is not None:
            current.completed_target_ids.add(selected.key())
            if selected.target_id:
                current.completed_target_ids.add(selected.target_id)
        current.complete_count += 1
        if current.complete_count >= completed_limit:
            return False
        current.last_message = message
        current.perception_deadline = __import__('time').monotonic() + max(perception_blocked_after_sec, 0.1)
        current.plan_deadline = 0.0
        current.execute_deadline = 0.0
        current.verify_deadline = 0.0
        current.target_id = None
        current.selected_target = None
        current.active_place_pose = {}
        current.stage = 'perception'
        engine.state.plan = []
        engine.state.pending_plan_request_id = ''
        engine.state.pending_execution_request_id = ''
        engine.state.last_plan_result = {}
        engine.state.last_execution_status = {}
        transition = engine._state_machine.retry_to_perception(f'{message}; continuing to next target')
        engine._hooks.emit_event(
            'INFO',
            'task_orchestrator',
            'TASK_CONTINUING',
            current.task_id,
            0,
            transition.reason,
            stage='perception',
        )
        engine.mark_task_terminal(
            current.task_id,
            state='running',
            result_code=0,
            message=transition.reason,
            elapsed=current.elapsed(),
        )
        return True


PLUGIN_REGISTRY: dict[str, TaskRuntimePlugin] = {
    'single_target': SingleTargetPlugin(),
    'selector_routed': SelectorRoutedPlugin(),
    'continuous': ContinuousPlugin(),
}


def resolve_task_runtime_plugin(task_type: str, *, metadata: dict[str, Any] | None = None) -> TaskRuntimePlugin:
    """Resolve the authoritative task-runtime plugin for one backend task type.

    Args:
        task_type: Backend task type stored in TaskRequest/TaskContext.
        metadata: Optional task metadata. ``pluginKey`` takes precedence when supplied.

    Returns:
        TaskRuntimePlugin: Registered runtime plugin. Unknown values fail closed
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
