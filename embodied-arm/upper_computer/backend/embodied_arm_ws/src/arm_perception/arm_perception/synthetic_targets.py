from __future__ import annotations

from typing import Any


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def extract_synthetic_targets(frame: Any, *, detector_name: str) -> list[dict[str, Any]]:
    """Extract structured synthetic targets from runtime camera summaries or raw frames."""
    normalized_detector = str(detector_name).strip().lower()
    if not normalized_detector:
        raise ValueError('detector_name must be non-empty')
    if not isinstance(frame, dict):
        return []
    candidate = frame
    if isinstance(frame.get('payload'), dict):
        candidate = frame['payload']
    elif isinstance(frame.get('frame'), dict) and isinstance(frame['frame'].get('payload'), dict):
        candidate = frame['frame']['payload']
    raw_targets = candidate.get('targets') or candidate.get('syntheticTargets') or []
    if not isinstance(raw_targets, list):
        return []
    results: list[dict[str, Any]] = []
    for item in raw_targets:
        if not isinstance(item, dict):
            continue
        detectors = item.get('detectors') or item.get('sources') or []
        normalized_detectors = {str(entry).strip().lower() for entry in detectors if str(entry).strip()}
        if normalized_detectors and normalized_detector not in normalized_detectors:
            continue
        target_id = str(item.get('target_id', item.get('id', ''))).strip()
        if not target_id:
            continue
        payload = {
            'target_id': target_id,
            'target_type': str(item.get('target_type', item.get('type', 'unknown'))),
            'semantic_label': str(item.get('semantic_label', item.get('label', item.get('target_type', 'unknown')))),
            'x': _safe_float(item.get('x', item.get('table_x', 0.0))),
            'y': _safe_float(item.get('y', item.get('table_y', 0.0))),
            'yaw': _safe_float(item.get('yaw', 0.0)),
            'confidence': _safe_float(item.get('confidence', 0.0)),
            'u': _safe_float(item.get('u', item.get('image_u', 0.0))),
            'v': _safe_float(item.get('v', item.get('image_v', 0.0))),
            'detector': normalized_detector,
        }
        if 'qr_text' in item:
            payload['qr_text'] = str(item.get('qr_text', ''))
        results.append(payload)
    return results
