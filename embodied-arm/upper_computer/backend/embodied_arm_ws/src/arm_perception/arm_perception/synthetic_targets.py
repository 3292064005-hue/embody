from __future__ import annotations

from typing import Any


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _frame_payload(frame: Any) -> dict[str, Any]:
    if not isinstance(frame, dict):
        return {}
    if isinstance(frame.get('payload'), dict):
        return dict(frame.get('payload') or {})
    if isinstance(frame.get('frame'), dict) and isinstance(frame['frame'].get('payload'), dict):
        return dict(frame['frame'].get('payload') or {})
    return dict(frame)


def describe_frame_visual_source(frame: Any) -> dict[str, Any]:
    """Return stable visual-source metadata for one runtime frame.

    Args:
        frame: Camera-runtime payload, raw frame dictionary, or nested frame
            summary.

    Returns:
        dict[str, Any]: Stable source metadata used by perception/gateway layers.

    Raises:
        Does not raise. Unknown inputs degrade to explicit conservative values.
    """
    payload = _frame_payload(frame)
    provenance = dict(payload.get('visualProvenance') or {}) if isinstance(payload.get('visualProvenance'), dict) else {}
    source_class = str(payload.get('sourceClass', provenance.get('sourceClass', 'unknown')) or 'unknown')
    detection_source_mode = str(payload.get('detectionSourceMode', provenance.get('detectionSourceMode', 'unknown')) or 'unknown')
    authoritative_target_source = str(payload.get('authoritativeTargetSource', provenance.get('authoritativeTargetSource', detection_source_mode)) or detection_source_mode)
    renderable_preview = bool(payload.get('renderablePreview', provenance.get('renderablePreview', False)))
    camera_live = bool(payload.get('cameraLive', provenance.get('cameraLive', source_class == 'live')))
    frame_ingress_live = bool(payload.get('frameIngressLive', provenance.get('frameIngressLive', camera_live)))
    return {
        'sourceClass': source_class,
        'detectionSourceMode': detection_source_mode,
        'authoritativeTargetSource': authoritative_target_source,
        'renderablePreview': renderable_preview,
        'cameraLive': camera_live,
        'frameIngressLive': frame_ingress_live,
    }


def _frame_allows_synthetic_targets(frame: Any) -> bool:
    payload = _frame_payload(frame)
    visual_source = describe_frame_visual_source(frame)
    detection_source_mode = visual_source['detectionSourceMode']
    authoritative_target_source = visual_source['authoritativeTargetSource']
    if detection_source_mode in {'real_image_required', 'external_topic_required'}:
        return False
    if authoritative_target_source in {'real_image_required', 'external_topic_required'}:
        return False
    if detection_source_mode == 'synthetic_targets' or authoritative_target_source == 'synthetic_perception':
        return True
    if visual_source['sourceClass'] == 'synthetic':
        return True
    raw_targets = payload.get('targets') or payload.get('syntheticTargets') or []
    return isinstance(raw_targets, list) and bool(raw_targets) and detection_source_mode in {'unknown', ''}


def extract_synthetic_targets(frame: Any, *, detector_name: str) -> list[dict[str, Any]]:
    """Extract structured synthetic targets from runtime camera summaries or raw frames.

    Boundary behavior:
        The extractor fails closed for frames that explicitly declare live-camera
        or external-detector provenance. This prevents metadata-only live frames
        from fabricating synthetic detections while preserving compatibility for
        legacy synthetic summaries that only carry ``targets``.
    """
    normalized_detector = str(detector_name).strip().lower()
    if not normalized_detector:
        raise ValueError('detector_name must be non-empty')
    if not isinstance(frame, dict):
        return []
    if not _frame_allows_synthetic_targets(frame):
        return []
    candidate = _frame_payload(frame)
    raw_targets = candidate.get('targets') or candidate.get('syntheticTargets') or []
    if not isinstance(raw_targets, list):
        return []
    visual_source = describe_frame_visual_source(frame)
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
            'detection_source_mode': str(visual_source['detectionSourceMode']),
            'authoritative_visual_source': str(visual_source['authoritativeTargetSource']),
        }
        if 'qr_text' in item:
            payload['qr_text'] = str(item.get('qr_text', ''))
        results.append(payload)
    return results
