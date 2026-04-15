from __future__ import annotations

"""Task capability catalog helpers.

This module exposes the generated task capability manifest as the single source
of truth for HMI task templates and task-start resolution. The gateway no
longer maintains an independent hand-written task template list.
"""

from dataclasses import dataclass
from functools import lru_cache
import json
from pathlib import Path
from typing import Any

from .generated.runtime_contract import PRODUCT_LINE_CAPABILITIES, TASK_CAPABILITY_TEMPLATES

_MANIFEST_PATH = Path(__file__).resolve().parents[1] / 'docs' / 'generated' / 'runtime_contract_manifest.json'


class TaskCapabilityPlugin:
    """Resolve one task template into one executable transport contract."""

    key = 'single_target'

    def resolve(self, template: dict[str, Any], target_category: str | None) -> tuple[str | None, str]:
        allowed_categories = [str(value) for value in template.get('allowedTargetCategories', []) if str(value).strip()]
        resolved_target = str(target_category).strip() if target_category not in (None, '') else None
        if allowed_categories:
            resolved_target = resolved_target or str(template.get('defaultTargetCategory', '') or '') or None
            if resolved_target not in allowed_categories:
                raise ValueError(
                    f"template {template['id']} does not allow target category {resolved_target!r}; "
                    f"allowed: {', '.join(allowed_categories)}"
                )
        else:
            resolved_target = None
        resolved_profiles = {str(key): str(value) for key, value in dict(template.get('resolvedPlaceProfiles', {}) or {}).items()}
        if resolved_target:
            place_profile = resolved_profiles.get(resolved_target)
            if not place_profile:
                raise ValueError(f"template {template['id']} does not define a place profile for target category {resolved_target!r}")
            return resolved_target, str(place_profile)
        return None, str(resolved_profiles.get('default', 'default') or 'default')


class SelectorRoutedPlugin(TaskCapabilityPlugin):
    key = 'selector_routed'


class ContinuousTaskPlugin(TaskCapabilityPlugin):
    key = 'continuous'

    def resolve(self, template: dict[str, Any], target_category: str | None) -> tuple[str | None, str]:
        del target_category
        resolved_profiles = {str(key): str(value) for key, value in dict(template.get('resolvedPlaceProfiles', {}) or {}).items()}
        return None, str(resolved_profiles.get('default', 'default') or 'default')


PLUGIN_REGISTRY: dict[str, TaskCapabilityPlugin] = {
    'single_target': TaskCapabilityPlugin(),
    'selector_routed': SelectorRoutedPlugin(),
    'continuous': ContinuousTaskPlugin(),
}


@dataclass(frozen=True)
class ResolvedTaskRequest:
    """Resolved task-start payload derived from the authoritative catalog.

    Attributes:
        template_id: Stable catalog template identifier.
        frontend_task_type: Public HMI task type.
        backend_task_type: Backend task type passed to ROS.
        target_category: Resolved selector/category or ``None``.
        place_profile: Resolved placement profile consumed by the runtime.
        required_runtime_tier: Minimum runtime tier required for the template.
        risk_level: Public operator-facing risk marker.
        task_profile_path: Backend task profile path declared by the catalog.
        plugin_key: Capability-plugin identifier used to resolve the request.
    """

    template_id: str
    frontend_task_type: str
    backend_task_type: str
    target_category: str | None
    place_profile: str
    required_runtime_tier: str
    risk_level: str
    task_profile_path: str
    plugin_key: str
    graph_key: str


def _fallback_manifest() -> dict[str, Any]:
    """Build one minimal manifest from the generated Python mirror.

    Returns:
        dict[str, Any]: Manifest payload compatible with the JSON artifact.

    Boundary behavior:
        - Used only when ``runtime_contract_manifest.json`` is unavailable or
          malformed.
        - Keeps the gateway operable from the checked-in generated mirror rather
          than failing at import time.
    """
    return {
        'runtime': {
            'productLineCapabilities': {
                str(key): dict(value) for key, value in PRODUCT_LINE_CAPABILITIES.items()
            },
        },
        'tasks': {
            'schemaVersion': 1,
            'productLines': {
                str(key): dict(value) for key, value in PRODUCT_LINE_CAPABILITIES.items()
            },
            'templates': [dict(item) for item in TASK_CAPABILITY_TEMPLATES],
        },
    }


@lru_cache(maxsize=1)
def _manifest() -> dict[str, Any]:
    """Load the generated runtime contract manifest.

    Returns:
        dict[str, Any]: Decoded manifest payload.

    Raises:
        RuntimeError: If neither the JSON artifact nor the generated Python
            mirror exposes a valid manifest payload.
    """
    if _MANIFEST_PATH.exists():
        payload = json.loads(_MANIFEST_PATH.read_text(encoding='utf-8'))
        if isinstance(payload, dict):
            return payload
        raise RuntimeError('task capability manifest must decode to an object')
    payload = _fallback_manifest()
    if not isinstance(payload, dict) or not payload.get('tasks', {}).get('templates'):
        raise RuntimeError(f'task capability manifest missing: {_MANIFEST_PATH}')
    return payload


@lru_cache(maxsize=1)
def _templates_by_id() -> dict[str, dict[str, Any]]:
    payload = _manifest().get('tasks', {})
    templates = payload.get('templates', []) if isinstance(payload, dict) else []
    indexed: dict[str, dict[str, Any]] = {}
    for item in templates:
        if isinstance(item, dict) and str(item.get('id', '')).strip():
            indexed[str(item['id'])] = dict(item)
    if not indexed:
        raise RuntimeError('task capability manifest does not expose any templates')
    return indexed


def public_task_templates() -> list[dict[str, Any]]:
    """Return public task templates for REST and frontend consumption.

    Returns:
        list[dict[str, Any]]: Stable task template payloads.

    Raises:
        RuntimeError: If the generated manifest is unavailable.
    """
    templates: list[dict[str, Any]] = []
    for item in _templates_by_id().values():
        templates.append({
            'id': str(item['id']),
            'name': str(item.get('name', item['id'])),
            'taskType': str(item.get('taskType', 'pick_place')),
            'description': str(item.get('description', '')),
            'defaultTargetCategory': item.get('defaultTargetCategory'),
            'allowedTargetCategories': list(item.get('allowedTargetCategories', []) or []),
            'resolvedPlaceProfiles': dict(item.get('resolvedPlaceProfiles', {}) or {}),
            'riskLevel': str(item.get('riskLevel', 'medium')),
            'requiredRuntimeTier': str(item.get('requiredRuntimeTier', 'validated_sim')),
            'operatorHint': str(item.get('operatorHint', '')),
            'capabilityTags': list(item.get('capabilityTags', []) or []),
            'preconditions': list(item.get('preconditions', []) or []),
            'sequenceMode': str(item.get('sequenceMode', 'single_target')),
            'pluginKey': str(item.get('pluginKey', item.get('sequenceMode', 'single_target')) or 'single_target'),
            'graphKey': str(item.get('graphKey', '') or ''),
            'taskGraph': dict(item.get('taskGraph', {}) or {}),
        })
    return templates


@lru_cache(maxsize=1)
def product_line_capabilities() -> dict[str, dict[str, Any]]:
    payload = _manifest().get('runtime', {})
    capabilities = payload.get('productLineCapabilities', {}) if isinstance(payload, dict) else {}
    return {str(key): dict(value) for key, value in capabilities.items() if isinstance(value, dict)}


@lru_cache(maxsize=1)
def task_capability_summary() -> dict[str, Any]:
    payload = _manifest().get('tasks', {})
    if not isinstance(payload, dict):
        return {'schemaVersion': 1, 'templates': [], 'productLines': {}}
    return {
        'schemaVersion': int(payload.get('schemaVersion', 1) or 1),
        'templates': public_task_templates(),
        'productLines': {
            str(key): dict(value)
            for key, value in (payload.get('productLines', {}) or {}).items()
            if isinstance(value, dict)
        },
    }


def resolve_task_request(*, template_id: str | None, task_type: str | None, target_category: str | None) -> ResolvedTaskRequest:
    """Resolve one public task-start request against the authoritative catalog.

    Args:
        template_id: Optional selected template identifier.
        task_type: Optional public task type for legacy clients.
        target_category: Optional public selector/category.

    Returns:
        ResolvedTaskRequest: Catalog-resolved task-start description.

    Raises:
        ValueError: If the template or requested category is unsupported.
    """
    templates = _templates_by_id()
    resolved_template: dict[str, Any] | None = None
    if template_id:
        resolved_template = templates.get(str(template_id))
        if resolved_template is None:
            raise ValueError(f'unknown task template: {template_id}')
        if task_type and str(resolved_template.get('taskType', '')) != str(task_type):
            raise ValueError('templateId and taskType do not match the same capability template')
    else:
        normalized_type = str(task_type or '').strip()
        if not normalized_type:
            raise ValueError('taskType or templateId is required')
        for item in templates.values():
            if str(item.get('taskType', '')) != normalized_type:
                continue
            allowed_categories = list(item.get('allowedTargetCategories', []) or [])
            default_category = item.get('defaultTargetCategory')
            if target_category and allowed_categories and str(target_category) in allowed_categories:
                resolved_template = item
                break
            if not target_category and (not allowed_categories or default_category is not None):
                resolved_template = item
                break
        if resolved_template is None:
            raise ValueError(f'unsupported taskType: {normalized_type}')

    plugin_key = str(resolved_template.get('pluginKey', resolved_template.get('sequenceMode', 'single_target')) or 'single_target')
    plugin = PLUGIN_REGISTRY.get(plugin_key)
    if plugin is None:
        raise ValueError(f'unknown task capability plugin: {plugin_key}')
    resolved_target, place_profile = plugin.resolve(resolved_template, target_category)

    return ResolvedTaskRequest(
        template_id=str(resolved_template['id']),
        frontend_task_type=str(resolved_template.get('taskType', 'pick_place')),
        backend_task_type=str(resolved_template.get('backendTaskType', 'PICK_AND_PLACE')),
        target_category=resolved_target,
        place_profile=str(place_profile or 'default'),
        required_runtime_tier=str(resolved_template.get('requiredRuntimeTier', 'validated_sim')),
        risk_level=str(resolved_template.get('riskLevel', 'medium')),
        task_profile_path=str(resolved_template.get('taskProfilePath', '')),
        plugin_key=plugin_key,
        graph_key=str(resolved_template.get('graphKey', resolved_template.get('id', 'unknown-task-graph'))),
    )
