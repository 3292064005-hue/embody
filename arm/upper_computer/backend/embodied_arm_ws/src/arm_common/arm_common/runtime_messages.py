from __future__ import annotations

"""Typed runtime message codecs with JSON compatibility fallbacks.

These helpers allow backend nodes to publish and consume new typed topics while
preserving the legacy JSON payload structure on compatibility topics.
"""

import json
from typing import Any

from .interface_compat import MsgTypes

ReadinessState = MsgTypes.ReadinessState
TaskStatusMsg = MsgTypes.TaskStatus
DiagnosticsSummary = MsgTypes.DiagnosticsSummary
BringupStatus = MsgTypes.BringupStatus
CalibrationProfileMsg = MsgTypes.CalibrationProfileMsg
TargetArray = MsgTypes.TargetArray
TargetInfo = MsgTypes.TargetInfo


def _parse_raw_json(raw_json: str) -> dict[str, Any]:
    if not raw_json:
        return {}
    try:
        payload = json.loads(raw_json)
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _ensure_instantiable(cls, name: str):
    if cls is object:
        raise TypeError(f'{name} interface type is unavailable')
    return cls


def _coerce_int(value: Any, default: int = 0) -> int:
    try:
        if value in (None, ''):
            return int(default)
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def _coerce_float(value: Any, default: float = 0.0) -> float:
    try:
        if value in (None, ''):
            return float(default)
        converted = float(value)
    except (TypeError, ValueError):
        return float(default)
    if converted != converted:  # NaN guard
        return float(default)
    return converted


def _coerce_bool(value: Any, default: bool = False) -> bool:
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


def _listify(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return [value]




def build_bringup_status_message(payload: dict[str, Any]):
    """Build a typed bringup-status shadow message.

    Args:
        payload: JSON-compatible bringup / lifecycle status payload.

    Returns:
        Instantiated ``BringupStatus`` ROS message.

    Raises:
        TypeError: If the typed ROS interface is unavailable.

    Boundary behavior:
        Unknown optional fields remain encoded in ``raw_json`` so the legacy JSON
        compatibility topic stays lossless during migration.
    """
    cls = _ensure_instantiable(BringupStatus, 'BringupStatus')
    data = payload if isinstance(payload, dict) else {}
    msg = cls()
    msg.ready = _coerce_bool(data.get('ready', data.get('allActive', False)))
    msg.managed_lifecycle = _coerce_bool(data.get('managedLifecycle', False))
    msg.autostart_complete = _coerce_bool(data.get('autostartComplete', msg.ready))
    msg.all_active = _coerce_bool(data.get('allActive', msg.ready))
    msg.current_layer = str(data.get('currentLayer', '') or '')
    msg.blocking_node = str(data.get('blockingNode', '') or '')
    msg.terminal_fault_reason = str(data.get('terminalFaultReason', '') or '')
    msg.raw_json = json.dumps(data, ensure_ascii=False)
    return msg


def parse_bringup_status_message(msg: Any) -> dict[str, Any]:
    payload = _parse_raw_json(str(getattr(msg, 'raw_json', '') or ''))
    payload.setdefault('ready', _coerce_bool(getattr(msg, 'ready', False)))
    payload.setdefault('managedLifecycle', _coerce_bool(getattr(msg, 'managed_lifecycle', False)))
    payload.setdefault('autostartComplete', _coerce_bool(getattr(msg, 'autostart_complete', payload.get('ready', False))))
    payload.setdefault('allActive', _coerce_bool(getattr(msg, 'all_active', payload.get('ready', False))))
    payload.setdefault('currentLayer', str(getattr(msg, 'current_layer', '') or ''))
    payload.setdefault('blockingNode', str(getattr(msg, 'blocking_node', '') or ''))
    payload.setdefault('terminalFaultReason', str(getattr(msg, 'terminal_fault_reason', '') or ''))
    return payload

def build_readiness_state_message(payload: dict[str, Any]):
    """Build a typed readiness snapshot message.

    Args:
        payload: JSON-compatible readiness snapshot dictionary.

    Returns:
        Instantiated ``ReadinessState`` ROS message.

    Raises:
        TypeError: If the typed ROS interface is unavailable in the current
            environment.

    Boundary behavior:
        Missing or malformed optional fields degrade to deterministic defaults
        instead of raising during runtime publication.
    """
    cls = _ensure_instantiable(ReadinessState, 'ReadinessState')
    snapshot = payload if isinstance(payload, dict) else {}
    msg = cls()
    msg.all_ready = _coerce_bool(snapshot.get('allReady', False))
    missing_checks = [str(item) for item in _listify(snapshot.get('missingChecks')) if str(item)]
    fallback_detail = ', '.join(missing_checks) if missing_checks else ('ready' if msg.all_ready else 'not_ready')
    msg.detail = str(snapshot.get('detail') or fallback_detail)
    msg.raw_json = json.dumps(snapshot, ensure_ascii=False)
    return msg


def parse_readiness_state_message(msg: Any) -> dict[str, Any]:
    payload = _parse_raw_json(str(getattr(msg, 'raw_json', '') or ''))
    if 'allReady' not in payload:
        payload['allReady'] = _coerce_bool(getattr(msg, 'all_ready', False))
    payload.setdefault('detail', str(getattr(msg, 'detail', '') or ''))
    return payload


def build_task_status_message(payload: dict[str, Any], *, stamp_factory=None):
    """Build a typed task-status message from a JSON-compatible payload.

    Args:
        payload: Task status mapping using gateway/backend compatibility keys.
        stamp_factory: Optional callable returning a ROS time message.

    Returns:
        Instantiated ``TaskStatus`` ROS message.

    Raises:
        TypeError: If the typed ROS interface is unavailable.

    Boundary behavior:
        Invalid numeric or boolean fields are coerced to conservative defaults
        instead of raising during publication.
    """
    cls = _ensure_instantiable(TaskStatusMsg, 'TaskStatus')
    data = payload if isinstance(payload, dict) else {}
    msg = cls()
    if stamp_factory is not None and hasattr(msg, 'stamp'):
        msg.stamp = stamp_factory()
    msg.task_id = str(data.get('taskId', data.get('task_id', '')) or '')
    msg.task_type = str(data.get('taskType', data.get('task_type', '')) or '')
    msg.stage = str(data.get('stage', '') or '')
    msg.target_id = str(data.get('targetId', data.get('target_id', '')) or '')
    msg.place_profile = str(data.get('placeProfile', data.get('place_profile', '')) or '')
    msg.retry_count = max(0, _coerce_int(data.get('retryCount', 0), 0))
    msg.max_retry = max(0, _coerce_int(data.get('maxRetry', 0), 0))
    msg.active = _coerce_bool(data.get('active', False))
    msg.cancel_requested = _coerce_bool(data.get('cancelRequested', False))
    msg.message = str(data.get('message', '') or '')
    msg.progress = _coerce_float(data.get('progress', data.get('percent', 0.0)), 0.0)
    return msg


def parse_task_status_message(msg: Any) -> dict[str, Any]:
    return {
        'taskId': str(getattr(msg, 'task_id', '') or ''),
        'taskType': str(getattr(msg, 'task_type', '') or ''),
        'stage': str(getattr(msg, 'stage', '') or ''),
        'targetId': str(getattr(msg, 'target_id', '') or ''),
        'placeProfile': str(getattr(msg, 'place_profile', '') or ''),
        'retryCount': _coerce_int(getattr(msg, 'retry_count', 0), 0),
        'maxRetry': _coerce_int(getattr(msg, 'max_retry', 0), 0),
        'active': _coerce_bool(getattr(msg, 'active', False)),
        'cancelRequested': _coerce_bool(getattr(msg, 'cancel_requested', False)),
        'message': str(getattr(msg, 'message', '') or ''),
        'progress': _coerce_float(getattr(msg, 'progress', 0.0), 0.0),
    }


def build_diagnostics_summary_message(payload: dict[str, Any]):
    """Build a typed diagnostics summary message.

    Args:
        payload: JSON-compatible diagnostics payload.

    Returns:
        Instantiated ``DiagnosticsSummary`` ROS message.

    Raises:
        TypeError: If the typed ROS interface is unavailable.

    Boundary behavior:
        Health-like string aliases and malformed numeric fields are normalized to
        stable booleans/numbers.
    """
    cls = _ensure_instantiable(DiagnosticsSummary, 'DiagnosticsSummary')
    data = payload if isinstance(payload, dict) else {}
    msg = cls()
    msg.ready = _coerce_bool(data.get('ready', False)) or str(data.get('health', '')).strip().lower() in {'ok', 'ready'}
    msg.detail = str(data.get('detail') or data.get('health') or '')
    msg.latency_ms = _coerce_float(data.get('latencyMs', 0.0), 0.0)
    msg.task_success_rate = _coerce_float(data.get('taskSuccessRate', 0.0), 0.0)
    return msg


def parse_diagnostics_summary_message(msg: Any) -> dict[str, Any]:
    detail = str(getattr(msg, 'detail', '') or '')
    ready = _coerce_bool(getattr(msg, 'ready', False))
    return {
        'ready': ready,
        'degraded': not ready,
        'detail': detail,
        'health': detail,
        'latencyMs': _coerce_float(getattr(msg, 'latency_ms', 0.0), 0.0),
        'taskSuccessRate': _coerce_float(getattr(msg, 'task_success_rate', 0.0), 0.0),
    }


def build_calibration_profile_message(payload: dict[str, Any]):
    """Build a typed calibration profile mirror message."""
    cls = _ensure_instantiable(CalibrationProfileMsg, 'CalibrationProfileMsg')
    data = payload if isinstance(payload, dict) else {}
    msg = cls()
    profile = dict(data.get('profile') or {})
    msg.profile_name = str(profile.get('version', 'default') or 'default')
    msg.raw_json = json.dumps(data, ensure_ascii=False)
    return msg


def parse_calibration_profile_message(msg: Any) -> dict[str, Any]:
    payload = _parse_raw_json(str(getattr(msg, 'raw_json', '') or ''))
    payload.setdefault('profile', {})
    if isinstance(payload.get('profile'), dict):
        payload['profile'].setdefault('version', str(getattr(msg, 'profile_name', '') or 'default'))
    return payload


def build_target_array_message(summary: dict[str, Any], *, stamp_factory=None):
    """Build a typed target-array summary from a compatibility target payload.

    Args:
        summary: Mapping containing a ``targets`` list.
        stamp_factory: Optional callable returning a ROS time message.

    Returns:
        Instantiated ``TargetArray`` message.

    Raises:
        TypeError: If typed target interfaces are unavailable.

    Boundary behavior:
        Non-dictionary target entries are skipped. Invalid coordinates or
        confidence values degrade to ``0.0`` instead of raising.
    """
    array_cls = _ensure_instantiable(TargetArray, 'TargetArray')
    target_cls = _ensure_instantiable(TargetInfo, 'TargetInfo')
    data = summary if isinstance(summary, dict) else {}
    msg = array_cls()
    if stamp_factory is not None and hasattr(msg, 'header'):
        msg.header.stamp = stamp_factory()
    typed_targets = []
    for item in _listify(data.get('targets')):
        if not isinstance(item, dict):
            continue
        target = target_cls()
        if hasattr(target, 'header') and stamp_factory is not None:
            target.header.stamp = stamp_factory()
        target.target_id = str(item.get('target_id', item.get('id', '')) or '')
        target.target_type = str(item.get('target_type', item.get('type', item.get('category', 'unknown'))) or 'unknown')
        target.semantic_label = str(item.get('semantic_label', item.get('label', item.get('category', target.target_type))) or target.target_type)
        target.image_u = _coerce_float(item.get('image_u', item.get('pixelX', item.get('u', 0.0))), 0.0)
        target.image_v = _coerce_float(item.get('image_v', item.get('pixelY', item.get('v', 0.0))), 0.0)
        target.table_x = _coerce_float(item.get('table_x', item.get('worldX', item.get('x', 0.0))), 0.0)
        target.table_y = _coerce_float(item.get('table_y', item.get('worldY', item.get('y', 0.0))), 0.0)
        target.yaw = _coerce_float(item.get('yaw', item.get('angle', 0.0)), 0.0)
        target.confidence = _coerce_float(item.get('confidence', 0.0), 0.0)
        target.is_valid = _coerce_bool(item.get('is_valid', item.get('graspable', target.confidence >= 0.5)))
        typed_targets.append(target)
    msg.targets = typed_targets
    return msg


def parse_target_array_message(msg: Any) -> dict[str, Any]:
    targets = []
    for item in list(getattr(msg, 'targets', []) or []):
        targets.append({
            'target_id': str(getattr(item, 'target_id', '') or ''),
            'target_type': str(getattr(item, 'target_type', '') or ''),
            'semantic_label': str(getattr(item, 'semantic_label', '') or ''),
            'image_u': _coerce_float(getattr(item, 'image_u', 0.0), 0.0),
            'image_v': _coerce_float(getattr(item, 'image_v', 0.0), 0.0),
            'table_x': _coerce_float(getattr(item, 'table_x', 0.0), 0.0),
            'table_y': _coerce_float(getattr(item, 'table_y', 0.0), 0.0),
            'yaw': _coerce_float(getattr(item, 'yaw', 0.0), 0.0),
            'confidence': _coerce_float(getattr(item, 'confidence', 0.0), 0.0),
            'is_valid': _coerce_bool(getattr(item, 'is_valid', False)),
        })
    return {
        'targets': targets,
        'targetCount': len(targets),
        'primaryTarget': targets[0] if targets else None,
    }
