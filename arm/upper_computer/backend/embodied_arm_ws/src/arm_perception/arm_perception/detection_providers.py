from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Protocol

from .synthetic_targets import _frame_payload, describe_frame_visual_source, extract_synthetic_targets


_DETECTION_SOURCE_HINTS = {
    'external_detections',
    'real_detector',
    'live_detector',
    'runtime_detector',
    'vision_runtime_service',
}

_DETECTOR_ALIASES = {
    'color': {'color', 'colour'},
    'qrcode': {'qrcode', 'qr', 'qr_code'},
    'contour': {'contour', 'shape'},
}


def _normalized_detector_aliases(detector_name: str) -> set[str]:
    normalized = str(detector_name or '').strip().lower()
    aliases = set(_DETECTOR_ALIASES.get(normalized, {normalized}))
    aliases.add(normalized)
    return {item for item in aliases if item}


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


class DetectionProvider(Protocol):
    provider_name: str

    def supports(self, frame: Any, *, detector_name: str) -> bool: ...

    def detect(self, frame: Any, *, detector_name: str) -> list[dict[str, Any]]: ...


@dataclass(frozen=True)
class SyntheticTargetProvider:
    provider_name: str = 'synthetic_targets'

    def supports(self, frame: Any, *, detector_name: str) -> bool:
        return bool(extract_synthetic_targets(frame, detector_name=detector_name))

    def detect(self, frame: Any, *, detector_name: str) -> list[dict[str, Any]]:
        return extract_synthetic_targets(frame, detector_name=detector_name)


@dataclass(frozen=True)
class ExternalDetectionProvider:
    provider_name: str = 'external_detections'

    def supports(self, frame: Any, *, detector_name: str) -> bool:
        payload = _frame_payload(frame)
        visual_source = describe_frame_visual_source(frame)
        detection_mode = str(visual_source.get('detectionSourceMode', 'unknown'))
        authoritative_source = str(visual_source.get('authoritativeTargetSource', detection_mode))
        source_class = str(visual_source.get('sourceClass', 'unknown'))
        raw = payload.get('detections') or payload.get('externalDetections') or payload.get('targetDetections') or []
        if not isinstance(raw, list) or not raw:
            return False
        if detection_mode in _DETECTION_SOURCE_HINTS or authoritative_source in _DETECTION_SOURCE_HINTS:
            return True
        return source_class in {'live', 'external_topic'}

    def detect(self, frame: Any, *, detector_name: str) -> list[dict[str, Any]]:
        if not self.supports(frame, detector_name=detector_name):
            return []
        payload = _frame_payload(frame)
        raw_items = payload.get('detections') or payload.get('externalDetections') or payload.get('targetDetections') or []
        if not isinstance(raw_items, list):
            return []
        visual_source = describe_frame_visual_source(frame)
        aliases = _normalized_detector_aliases(detector_name)
        results: list[dict[str, Any]] = []
        for item in raw_items:
            if not isinstance(item, dict):
                continue
            declared = {str(item.get('detector', '')), *(str(v) for v in (item.get('detectors') or [])), *(str(v) for v in (item.get('sources') or []))}
            normalized_declared = {entry.strip().lower() for entry in declared if entry and entry.strip()}
            if normalized_declared and normalized_declared.isdisjoint(aliases):
                continue
            target_id = str(item.get('target_id', item.get('id', ''))).strip()
            if not target_id:
                continue
            confidence = _safe_float(item.get('confidence', 0.0))
            if confidence <= 0.0:
                continue
            result = {
                'target_id': target_id,
                'target_type': str(item.get('target_type', item.get('type', 'unknown')) or 'unknown'),
                'semantic_label': str(item.get('semantic_label', item.get('label', item.get('target_type', 'unknown'))) or 'unknown'),
                'x': _safe_float(item.get('x', item.get('table_x', 0.0))),
                'y': _safe_float(item.get('y', item.get('table_y', 0.0))),
                'yaw': _safe_float(item.get('yaw', 0.0)),
                'confidence': confidence,
                'u': _safe_float(item.get('u', item.get('image_u', 0.0))),
                'v': _safe_float(item.get('v', item.get('image_v', 0.0))),
                'detector': str(detector_name or '').strip().lower(),
                'detection_source_mode': str(visual_source['detectionSourceMode']),
                'authoritative_visual_source': str(visual_source['authoritativeTargetSource']),
                'detection_provider': self.provider_name,
            }
            if 'qr_text' in item:
                result['qr_text'] = str(item.get('qr_text', ''))
            results.append(result)
        return results


_DEFAULT_PROVIDERS: tuple[DetectionProvider, ...] = (ExternalDetectionProvider(), SyntheticTargetProvider())


def detect_targets(frame: Any, *, detector_name: str, providers: Iterable[DetectionProvider] | None = None) -> list[dict[str, Any]]:
    normalized = str(detector_name or '').strip().lower()
    if not normalized:
        raise ValueError('detector_name must be non-empty')
    active_providers = tuple(providers or _DEFAULT_PROVIDERS)
    for provider in active_providers:
        if provider.supports(frame, detector_name=normalized):
            results = provider.detect(frame, detector_name=normalized)
            if results:
                return results
    return []
