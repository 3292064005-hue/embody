from __future__ import annotations

"""Gateway-side decoders for typed shadow topics and legacy JSON fallbacks."""

import json
from typing import Any


def _decode_json_string(raw: str) -> dict[str, Any]:
    try:
        payload = json.loads(raw) if raw else {}
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


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


def decode_readiness_message(msg: Any) -> dict[str, Any]:
    if hasattr(msg, 'raw_json'):
        payload = _decode_json_string(str(getattr(msg, 'raw_json', '') or ''))
        if 'allReady' not in payload:
            payload['allReady'] = _coerce_bool(getattr(msg, 'all_ready', False))
        payload.setdefault('detail', str(getattr(msg, 'detail', '') or ''))
        return payload
    return _decode_json_string(str(getattr(msg, 'data', '') or ''))


def decode_task_status_message(msg: Any) -> dict[str, Any]:
    if hasattr(msg, 'task_id'):
        return {
            'taskId': str(getattr(msg, 'task_id', '') or ''),
            'taskType': str(getattr(msg, 'task_type', '') or ''),
            'stage': str(getattr(msg, 'stage', '') or ''),
            'targetId': str(getattr(msg, 'target_id', '') or ''),
            'placeProfile': str(getattr(msg, 'place_profile', '') or ''),
            'retryCount': max(0, _coerce_int(getattr(msg, 'retry_count', 0), 0)),
            'maxRetry': max(0, _coerce_int(getattr(msg, 'max_retry', 0), 0)),
            'active': _coerce_bool(getattr(msg, 'active', False)),
            'cancelRequested': _coerce_bool(getattr(msg, 'cancel_requested', False)),
            'message': str(getattr(msg, 'message', '') or ''),
            'progress': _coerce_float(getattr(msg, 'progress', 0.0), 0.0),
        }
    return _decode_json_string(str(getattr(msg, 'data', '') or ''))


def decode_diagnostics_summary_message(msg: Any) -> dict[str, Any]:
    if hasattr(msg, 'ready') and hasattr(msg, 'detail'):
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
    return _decode_json_string(str(getattr(msg, 'data', '') or ''))


def decode_calibration_profile_message(msg: Any) -> dict[str, Any]:
    if hasattr(msg, 'raw_json'):
        payload = _decode_json_string(str(getattr(msg, 'raw_json', '') or ''))
        payload.setdefault('profile', {})
        profile = payload['profile'] if isinstance(payload.get('profile'), dict) else {}
        profile.setdefault('version', str(getattr(msg, 'profile_name', '') or 'default'))
        payload['profile'] = profile
        return payload
    return _decode_json_string(str(getattr(msg, 'data', '') or ''))


def decode_target_array_message(msg: Any) -> dict[str, Any]:
    if hasattr(msg, 'targets'):
        converted = []
        for item in list(getattr(msg, 'targets', []) or []):
            converted.append({
                'id': str(getattr(item, 'target_id', '') or ''),
                'category': str(getattr(item, 'semantic_label', getattr(item, 'target_type', 'unknown')) or 'unknown'),
                'pixelX': _coerce_float(getattr(item, 'image_u', 0.0), 0.0),
                'pixelY': _coerce_float(getattr(item, 'image_v', 0.0), 0.0),
                'worldX': _coerce_float(getattr(item, 'table_x', 0.0), 0.0),
                'worldY': _coerce_float(getattr(item, 'table_y', 0.0), 0.0),
                'angle': _coerce_float(getattr(item, 'yaw', 0.0), 0.0),
                'confidence': _coerce_float(getattr(item, 'confidence', 0.0), 0.0),
                'graspable': _coerce_bool(getattr(item, 'is_valid', False)),
            })
        return {'targets': converted, 'targetCount': len(converted)}
    return _decode_json_string(str(getattr(msg, 'data', '') or ''))
