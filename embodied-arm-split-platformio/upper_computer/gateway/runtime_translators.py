from __future__ import annotations

"""Topic-family translation helpers for gateway runtime ingestion.

The bridge remains responsible for ROS transport wiring, while this module owns
payload-to-state projection for typed shadow topics and legacy compatibility
payloads.
"""

from typing import Any

from .models import now_iso
from .runtime_publisher import RuntimeEventPublisher
from .state import GatewayState


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        if value in (None, ''):
            return int(default)
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value in (None, ''):
            return float(default)
        converted = float(value)
    except (TypeError, ValueError):
        return float(default)
    if converted != converted:
        return float(default)
    return converted


def _safe_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return bool(default)
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {'true', '1', 'yes', 'on', 'ok', 'ready'}:
            return True
        if normalized in {'false', '0', 'no', 'off', 'fault', 'degraded', ''}:
            return False
    return bool(value)


def apply_targets_payload(state: GatewayState, publisher: RuntimeEventPublisher, payload: dict[str, Any]) -> bool:
    if not isinstance(payload, dict):
        return False
    targets = payload.get('targets', [])
    if not isinstance(targets, list):
        return False
    converted = []
    for item in targets:
        if not isinstance(item, dict):
            continue
        converted.append({
            'id': str(item.get('target_id', item.get('id', '')) or ''),
            'category': str(item.get('semantic_label', item.get('category', item.get('target_type', 'unknown'))) or 'unknown'),
            'pixelX': _safe_float(item.get('image_u', item.get('pixelX', item.get('u', 0.0))), 0.0),
            'pixelY': _safe_float(item.get('image_v', item.get('pixelY', item.get('v', 0.0))), 0.0),
            'worldX': _safe_float(item.get('table_x', item.get('worldX', item.get('x', 0.0))), 0.0),
            'worldY': _safe_float(item.get('table_y', item.get('worldY', item.get('y', 0.0))), 0.0),
            'angle': _safe_float(item.get('yaw', item.get('angle', 0.0)), 0.0),
            'confidence': _safe_float(item.get('confidence', 0.0), 0.0),
            'graspable': _safe_bool(item.get('is_valid', item.get('graspable', _safe_float(item.get('confidence', 0.0), 0.0) >= 0.5))),
            '_receivedAt': now_iso(),
        })
    if not converted:
        return False
    state.replace_targets(converted)
    publisher.publish_topics_threadsafe('targets', 'readiness', 'diagnostics')
    return True


def apply_task_status_payload(state: GatewayState, publisher: RuntimeEventPublisher, payload: dict[str, Any]) -> bool:
    if not isinstance(payload, dict):
        return False
    current = state.get_current_task() or {}
    current.update({
        'taskId': payload.get('taskId') or current.get('taskId'),
        'taskType': payload.get('taskType') or current.get('taskType') or 'pick_place',
        'stage': payload.get('stage') or current.get('stage') or 'created',
        'percent': max(0, _safe_int(payload.get('progress', current.get('percent', 0)), 0)),
        'retryCount': max(0, _safe_int(payload.get('retryCount', current.get('retryCount', 0)), 0)),
        'lastMessage': payload.get('message') or current.get('lastMessage') or '',
    })
    state.set_current_task(current if current.get('taskId') else None)
    publisher.publish_topics_threadsafe('task')
    return True


def apply_diagnostics_payload(state: GatewayState, publisher: RuntimeEventPublisher, payload: dict[str, Any]) -> bool:
    if not isinstance(payload, dict):
        return False
    diagnostics = state.get_diagnostics()
    ready = _safe_bool(payload.get('ready', not _safe_bool(payload.get('degraded', False))), diagnostics.get('ready', False))
    degraded = _safe_bool(payload.get('degraded', not ready), diagnostics.get('degraded', True))
    latency_value = payload.get('latencyMs', diagnostics.get('latencyMs'))
    success_rate_value = payload.get('taskSuccessRate', diagnostics.get('taskSuccessRate'))
    diagnostics.update({
        'ready': ready,
        'degraded': degraded,
        'detail': str(payload.get('detail') or payload.get('health') or diagnostics.get('detail') or ''),
        'latencyMs': _safe_float(latency_value, diagnostics.get('latencyMs') or 0.0) if latency_value is not None else None,
        'taskSuccessRate': _safe_float(success_rate_value, diagnostics.get('taskSuccessRate') or 0.0) if success_rate_value is not None else None,
        'updatedAt': now_iso(),
    })
    state.set_diagnostics(diagnostics, authoritative=True)
    publisher.publish_topics_threadsafe('diagnostics')
    return True


def apply_calibration_payload(state: GatewayState, publisher: RuntimeEventPublisher, payload: dict[str, Any]) -> bool:
    if not isinstance(payload, dict):
        return False
    profile = payload.get('profile', {})
    profile = profile if isinstance(profile, dict) else {}
    metadata_source = payload.get('hmi_metadata')
    if not isinstance(metadata_source, dict):
        metadata_source = profile.get('hmi_metadata') if isinstance(profile.get('hmi_metadata'), dict) else {}
    calibration = {
        'profileName': str(profile.get('version', 'default')),
        'roi': metadata_source.get('roi', {'x': 0, 'y': 0, 'width': 640, 'height': 480}),
        'tableScaleMmPerPixel': _safe_float(metadata_source.get('tableScaleMmPerPixel', 1.0), 1.0),
        'offsets': metadata_source.get('offsets', {'x': _safe_float(profile.get('x_bias', 0.0), 0.0), 'y': _safe_float(profile.get('y_bias', 0.0), 0.0), 'z': 0.0}),
        'updatedAt': str(metadata_source.get('updatedAt', '')) or '',
    }
    state.set_calibration(calibration)
    publisher.publish_topics_threadsafe('calibration', 'readiness', 'diagnostics')
    return True


def apply_readiness_payload(state: GatewayState, publisher: RuntimeEventPublisher, payload: dict[str, Any]) -> bool:
    if not isinstance(payload, dict):
        return False
    state.set_readiness_snapshot(payload)
    publisher.publish_topics_threadsafe('readiness', 'diagnostics')
    return True


__all__ = [
    'apply_calibration_payload',
    'apply_diagnostics_payload',
    'apply_readiness_payload',
    'apply_targets_payload',
    'apply_task_status_payload',
]
