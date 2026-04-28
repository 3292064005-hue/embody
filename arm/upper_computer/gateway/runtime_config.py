from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
from threading import RLock
from typing import Any, Callable, Generic, TypeVar

import yaml

from runtime_authority import (
    RUNTIME_AUTHORITY_PATH as CANONICAL_RUNTIME_AUTHORITY_PATH,
    RUNTIME_LANE_ALIASES_PATH as CANONICAL_RUNTIME_LANE_ALIASES_PATH,
    RUNTIME_PROFILES_PATH as CANONICAL_RUNTIME_PROFILES_PATH,
    VALIDATED_LIVE_EVIDENCE_PATH as CANONICAL_VALIDATED_LIVE_EVIDENCE_PATH,
    effective_target_runtime_gate_path,
    evaluate_promotion_receipt,
    load_runtime_authority,
    load_validated_live_evidence,
)

GATEWAY_ROOT = Path(__file__).resolve().parents[1]
BACKEND_CONFIG_DIR = GATEWAY_ROOT / 'backend' / 'embodied_arm_ws' / 'src' / 'arm_bringup' / 'config'
PLACEMENT_PROFILE_PATH = BACKEND_CONFIG_DIR / 'placement_profiles.yaml'
DEFAULT_CALIBRATION_PATH = BACKEND_CONFIG_DIR / 'default_calibration.yaml'
RUNTIME_PROMOTION_RECEIPT_PATH = BACKEND_CONFIG_DIR / 'runtime_promotion_receipts.yaml'
RUNTIME_PROFILE_PATH = CANONICAL_RUNTIME_PROFILES_PATH
RUNTIME_LANE_ALIAS_PATH = CANONICAL_RUNTIME_LANE_ALIASES_PATH
RUNTIME_AUTHORITY_PATH = CANONICAL_RUNTIME_AUTHORITY_PATH
VALIDATED_LIVE_EVIDENCE_PATH = CANONICAL_VALIDATED_LIVE_EVIDENCE_PATH
RELEASE_GATE_REPORT_PATH = effective_target_runtime_gate_path()
SAFETY_LIMITS_PATH = BACKEND_CONFIG_DIR / 'safety_limits.yaml'
FIRMWARE_SEMANTIC_PROFILES_PATH = BACKEND_CONFIG_DIR / 'firmware_semantic_profiles.yaml'

_DEFAULT_PLACE_PROFILES: dict[str, dict[str, float]] = {
    'default': {'x': 0.20, 'y': 0.00, 'yaw': 0.0},
    'bin_red': {'x': 0.25, 'y': 0.12, 'yaw': 0.0},
    'bin_blue': {'x': 0.25, 'y': -0.12, 'yaw': 0.0},
    'bin_green': {'x': 0.22, 'y': 0.02, 'yaw': 0.0},
}

_DEFAULT_MANUAL_COMMAND_LIMITS: dict[str, float] = {
    'max_servo_cartesian_delta': 0.1,
    'max_jog_joint_step_deg': 10.0,
}

_DEFAULT_RELEASE_GATES: dict[str, Any] = {
    'repoGate': 'not_executed',
    'targetGate': 'not_executed',
    'hilGate': 'not_executed',
    'releaseChecklistGate': 'not_executed',
    'releaseGate': 'not_executed',
    'hasBlockingStep': False,
    'blockingSteps': {},
}

T = TypeVar('T')


@dataclass(frozen=True)
class _FileSignature:
    tokens: tuple[tuple[str, bool, int, int], ...]


@dataclass
class _CachedValue(Generic[T]):
    signature: _FileSignature
    value: T


class _ConfigFileCache(Generic[T]):
    """Cache one parsed config file while still auto-refreshing on file change.

    The cache key is the file signature (existence, mtime, size). Callers get a
    fresh parse whenever the on-disk config changes, while stable files reuse the
    last parsed payload.
    """

    def __init__(self, path_getter: Callable[[], Path | tuple[Path, ...]], default_factory: Callable[[], T], parser: Callable[[Any], T]):
        self._path_getter = path_getter
        self._default_factory = default_factory
        self._parser = parser
        self._entry: _CachedValue[T] | None = None
        self._lock = RLock()

    def load(self) -> T:
        paths = self._paths()
        signature = self._signature(paths)
        with self._lock:
            if self._entry is not None and self._entry.signature == signature:
                return self._clone(self._entry.value)
            value = self._read(paths[0])
            self._entry = _CachedValue(signature=signature, value=value)
            return self._clone(value)

    def clear(self) -> None:
        with self._lock:
            self._entry = None

    def version(self) -> str:
        paths = self._paths()
        signature = self._signature(paths)
        return '|'.join(f'{name}:{int(exists)}:{mtime}:{size}' for name, exists, mtime, size in signature.tokens)

    def _read(self, path: Path) -> T:
        try:
            payload = yaml.safe_load(path.read_text(encoding='utf-8')) if path.exists() else None
        except Exception:
            return self._default_factory()
        try:
            return self._parser(payload)
        except Exception:
            return self._default_factory()

    def _paths(self) -> tuple[Path, ...]:
        value = self._path_getter()
        if isinstance(value, tuple):
            return value
        return (value,)

    @staticmethod
    def _signature(paths: tuple[Path, ...]) -> _FileSignature:
        tokens: list[tuple[str, bool, int, int]] = []
        for path in paths:
            try:
                stat = path.stat()
                tokens.append((path.name, True, int(stat.st_mtime_ns), int(stat.st_size)))
            except Exception:
                tokens.append((path.name, False, 0, 0))
        return _FileSignature(tuple(tokens))

    @staticmethod
    def _clone(value: T) -> T:
        if isinstance(value, dict):
            return {key: _ConfigFileCache._clone(item) for key, item in value.items()}  # type: ignore[return-value]
        if isinstance(value, list):
            return [_ConfigFileCache._clone(item) for item in value]  # type: ignore[return-value]
        return value


def _parse_place_profiles(payload: Any) -> dict[str, dict[str, float]]:
    profiles = payload.get('place_profiles', payload) if isinstance(payload, dict) else {}
    if not isinstance(profiles, dict):
        return {key: dict(value) for key, value in _DEFAULT_PLACE_PROFILES.items()}
    normalized: dict[str, dict[str, float]] = {}
    for name, profile in profiles.items():
        if not isinstance(profile, dict):
            continue
        normalized[str(name)] = {
            'x': float(profile.get('x', 0.0)),
            'y': float(profile.get('y', 0.0)),
            'yaw': float(profile.get('yaw', 0.0)),
        }
    return normalized or {key: dict(value) for key, value in _DEFAULT_PLACE_PROFILES.items()}


def _parse_default_calibration(payload: Any) -> dict[str, Any]:
    return payload if isinstance(payload, dict) else {}


def _load_runtime_authority_payload() -> dict[str, Any]:
    try:
        return load_runtime_authority(RUNTIME_AUTHORITY_PATH)
    except Exception:
        return {}


def _load_validated_live_evidence_payload() -> dict[str, Any]:
    return load_validated_live_evidence(VALIDATED_LIVE_EVIDENCE_PATH)


def _parse_runtime_profile_catalog(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {'lanes': {}, 'aliases': {}}
    lanes = {str(name): dict(item) for name, item in payload.items() if isinstance(item, dict)}
    return {'lanes': lanes, 'aliases': {}}


def _parse_runtime_lane_aliases(payload: Any) -> dict[str, str]:
    if not isinstance(payload, dict):
        return {}
    resolved = payload.get('resolved', {}) if isinstance(payload.get('resolved'), dict) else {}
    active = resolved.get('active', {}) if isinstance(resolved.get('active'), dict) else {}
    return {str(name): str(value) for name, value in active.items() if str(name).strip() and str(value).strip()}


def _parse_release_gate_details(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return dict(_DEFAULT_RELEASE_GATES)
    result = dict(_DEFAULT_RELEASE_GATES)
    for key in ('repoGate', 'targetGate', 'hilGate', 'releaseChecklistGate', 'releaseGate'):
        value = str(payload.get(key, result[key]) or result[key]).strip() or result[key]
        result[key] = value
    result['hasBlockingStep'] = bool(payload.get('hasBlockingStep', False))
    blocking = payload.get('blockingSteps', {}) if isinstance(payload.get('blockingSteps'), dict) else {}
    result['blockingSteps'] = {str(name): str(status) for name, status in blocking.items() if str(name).strip()}
    return result


def _parse_firmware_semantic_profiles(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {'esp32': {'default_profile': 'preview_reserved', 'profiles': {}}}
    esp32 = payload.get('esp32', {}) if isinstance(payload.get('esp32'), dict) else {}
    profiles = esp32.get('profiles', {}) if isinstance(esp32.get('profiles'), dict) else {}
    return {
        'esp32': {
            'default_profile': str(esp32.get('default_profile', 'preview_reserved') or 'preview_reserved'),
            'profiles': {str(name): dict(item) for name, item in profiles.items() if isinstance(item, dict)},
        }
    }


def _parse_runtime_promotion_receipt_details(payload: Any) -> dict[str, dict[str, Any]]:
    defaults = {
        'validated_sim': {
            'promotion_mode': 'manual',
            'promoted': True,
            'receipt_id': 'validated-sim-baseline',
            'checked_by': 'repository-ci',
            'checked_at': '2026-04-08T00:00:00Z',
            'required_evidence': ['backend-active', 'gateway', 'contract-artifacts', 'runtime-contracts'],
            'evidence': ['backend-active', 'gateway', 'contract-artifacts', 'runtime-contracts'],
            'reason': '',
            'effective': True,
            'missing_evidence': [],
        },
        'validated_live': {
            'promotion_mode': 'automatic_when_ready',
            'promoted': False,
            'receipt_id': '',
            'checked_by': '',
            'checked_at': '',
            'required_evidence': ['validated_live_backbone_declared', 'target_runtime_gate_passed', 'hil_gate_passed', 'release_checklist_signed'],
            'evidence': [],
            'reason': 'fail_closed_until_promotion_receipt_is_committed',
            'effective': False,
            'missing_evidence': ['validated_live_backbone_declared', 'target_runtime_gate_passed', 'hil_gate_passed', 'release_checklist_signed'],
        },
    }
    if not isinstance(payload, dict):
        return {key: dict(value) for key, value in defaults.items()}
    authority = _load_runtime_authority_payload()
    evidence_manifest = _load_validated_live_evidence_payload()
    result = {key: dict(value) for key, value in defaults.items()}
    for name, value in payload.items():
        if not isinstance(value, dict):
            continue
        status = evaluate_promotion_receipt({**value, 'tier_name': str(name)}, authority=authority, evidence_manifest=evidence_manifest)
        result[str(name)] = {
            'promotion_mode': status.mode,
            'promoted': bool(status.promoted),
            'receipt_id': str(value.get('receipt_id', '') or (f'{name}-auto-promotion' if status.mode == 'automatic_when_ready' and status.effective else '')),
            'checked_by': str(value.get('checked_by', '') or ('runtime-authority-auto-promoter' if status.mode == 'automatic_when_ready' and status.effective else '')),
            'checked_at': str(value.get('checked_at', '') or ('automatic_when_ready' if status.mode == 'automatic_when_ready' and status.effective else '')),
            'required_evidence': [str(item) for item in value.get('required_evidence', []) if str(item).strip()],
            'evidence': [str(item) for item in value.get('evidence', []) if str(item).strip()],
            'reason': str(value.get('reason', '') or ''),
            'effective': bool(status.effective),
            'missing_evidence': [str(item) for item in status.missing if str(item).strip()],
            'auto_generated': bool(status.mode == 'automatic_when_ready' and status.effective),
        }
    return result


def _parse_manual_command_limits(payload: Any) -> dict[str, float]:
    manual = payload.get('manual_command_limits', {}) if isinstance(payload, dict) else {}
    if not isinstance(manual, dict):
        return dict(_DEFAULT_MANUAL_COMMAND_LIMITS)
    return {
        'max_servo_cartesian_delta': float(manual.get('max_servo_cartesian_delta', _DEFAULT_MANUAL_COMMAND_LIMITS['max_servo_cartesian_delta'])),
        'max_jog_joint_step_deg': float(manual.get('max_jog_joint_step_deg', _DEFAULT_MANUAL_COMMAND_LIMITS['max_jog_joint_step_deg'])),
    }


_PLACE_PROFILE_CACHE = _ConfigFileCache(lambda: PLACEMENT_PROFILE_PATH, lambda: {key: dict(value) for key, value in _DEFAULT_PLACE_PROFILES.items()}, _parse_place_profiles)
_DEFAULT_CALIBRATION_CACHE = _ConfigFileCache(lambda: DEFAULT_CALIBRATION_PATH, dict, _parse_default_calibration)
_RUNTIME_PROMOTION_RECEIPT_CACHE = _ConfigFileCache(
    lambda: (RUNTIME_PROMOTION_RECEIPT_PATH, RUNTIME_AUTHORITY_PATH, VALIDATED_LIVE_EVIDENCE_PATH),
    lambda: _parse_runtime_promotion_receipt_details(None),
    _parse_runtime_promotion_receipt_details,
)
_RUNTIME_PROFILE_CACHE = _ConfigFileCache(lambda: RUNTIME_PROFILE_PATH, lambda: _parse_runtime_profile_catalog(None), _parse_runtime_profile_catalog)
_RUNTIME_LANE_ALIAS_CACHE = _ConfigFileCache(lambda: RUNTIME_LANE_ALIAS_PATH, dict, _parse_runtime_lane_aliases)
_RELEASE_GATE_CACHE = _ConfigFileCache(lambda: effective_target_runtime_gate_path(), lambda: dict(_DEFAULT_RELEASE_GATES), _parse_release_gate_details)
_FIRMWARE_SEMANTIC_PROFILE_CACHE = _ConfigFileCache(lambda: FIRMWARE_SEMANTIC_PROFILES_PATH, lambda: _parse_firmware_semantic_profiles(None), _parse_firmware_semantic_profiles)
_MANUAL_COMMAND_LIMITS_CACHE = _ConfigFileCache(lambda: SAFETY_LIMITS_PATH, lambda: dict(_DEFAULT_MANUAL_COMMAND_LIMITS), _parse_manual_command_limits)


def clear_runtime_config_caches() -> None:
    """Drop all runtime-config caches.

    Useful for tests or explicit admin refresh paths. Normal production code does
    not need to call this because loaders auto-refresh on file signature changes.
    """
    _PLACE_PROFILE_CACHE.clear()
    _DEFAULT_CALIBRATION_CACHE.clear()
    _RUNTIME_PROMOTION_RECEIPT_CACHE.clear()
    _RUNTIME_PROFILE_CACHE.clear()
    _RUNTIME_LANE_ALIAS_CACHE.clear()
    _RELEASE_GATE_CACHE.clear()
    _FIRMWARE_SEMANTIC_PROFILE_CACHE.clear()
    _MANUAL_COMMAND_LIMITS_CACHE.clear()


def current_runtime_config_version() -> str:
    """Return a stable version string derived from runtime-config file signatures."""
    parts = [
        _PLACE_PROFILE_CACHE.version(),
        _DEFAULT_CALIBRATION_CACHE.version(),
        _RUNTIME_PROMOTION_RECEIPT_CACHE.version(),
        _RUNTIME_PROFILE_CACHE.version(),
        _RUNTIME_LANE_ALIAS_CACHE.version(),
        _RELEASE_GATE_CACHE.version(),
        _FIRMWARE_SEMANTIC_PROFILE_CACHE.version(),
        _MANUAL_COMMAND_LIMITS_CACHE.version(),
    ]
    return '|'.join(parts)


def load_place_profiles() -> dict[str, dict[str, float]]:
    """Load authoritative placement profiles from backend config.

    Returns:
        dict[str, dict[str, float]]: Normalized place-profile map keyed by profile name.

    Raises:
        Does not raise. Invalid or missing config degrades to built-in defaults.
    """
    return _PLACE_PROFILE_CACHE.load()


def load_default_calibration_payload() -> dict[str, Any]:
    """Load the read-only default calibration YAML used by compatibility fallbacks."""
    return _DEFAULT_CALIBRATION_CACHE.load()


def load_runtime_promotion_receipt_details() -> dict[str, dict[str, Any]]:
    """Load detailed runtime-promotion receipts from backend config.

    Returns:
        dict[str, dict[str, Any]]: Detailed receipt metadata including effective
        promotion state and missing evidence markers.

    Raises:
        Does not raise. Missing or invalid config degrades to fail-closed defaults.
    """
    return _RUNTIME_PROMOTION_RECEIPT_CACHE.load()


def load_runtime_promotion_receipts() -> dict[str, bool]:
    """Load effective runtime-promotion receipts from backend config.

    Returns:
        dict[str, bool]: Effective public-tier promotion booleans keyed by runtime tier.

    Raises:
        Does not raise. Missing or invalid config degrades to fail-closed defaults.
    """
    details = load_runtime_promotion_receipt_details()
    return {str(name): bool(item.get('effective', item.get('promoted', False))) for name, item in details.items() if isinstance(item, dict)}


def load_runtime_profile_catalog() -> dict[str, Any]:
    """Load the generated runtime profile catalog and alias map."""
    catalog = _RUNTIME_PROFILE_CACHE.load()
    catalog['aliases'] = _RUNTIME_LANE_ALIAS_CACHE.load()
    return catalog


def resolve_active_runtime_profile(requested_profile: str | None = None) -> dict[str, Any]:
    """Resolve the active runtime profile from environment / alias configuration.

    Args:
        requested_profile: Optional runtime-profile token. Defaults to the
            `EMBODIED_ARM_RUNTIME_PROFILE` environment variable.

    Returns:
        dict[str, Any]: Requested token, resolved lane name, and active lane payload.

    Boundary behavior:
        Unknown aliases fail closed by returning an empty active profile rather
        than pretending that the default preview lane is authoritative.
    """
    catalog = load_runtime_profile_catalog()
    lanes = catalog.get('lanes', {}) if isinstance(catalog.get('lanes'), dict) else {}
    aliases = catalog.get('aliases', {}) if isinstance(catalog.get('aliases'), dict) else {}
    requested = str(requested_profile or os.environ.get('EMBODIED_ARM_RUNTIME_PROFILE', '') or '').strip()
    resolved = requested if requested in lanes else str(aliases.get(requested.lower(), '') or '')
    active = dict(lanes.get(resolved, {}) or {})
    return {
        'requestedProfile': requested,
        'activeRuntimeLane': resolved,
        'activeProfile': active,
        'resolvedFromAlias': bool(requested and requested not in lanes and resolved),
    }


def load_release_gate_details() -> dict[str, Any]:
    """Load the machine-readable release-gate projection."""
    return _RELEASE_GATE_CACHE.load()


def load_firmware_semantic_profiles() -> dict[str, Any]:
    """Load authoritative firmware semantic profiles."""
    return _FIRMWARE_SEMANTIC_PROFILE_CACHE.load()


def load_manual_command_limits() -> dict[str, float]:
    """Load manual-command limits shared by Gateway and backend runtime guards.

    Boundary behavior:
        The loader auto-refreshes when ``safety_limits.yaml`` changes on disk.
        Invalid or unreadable config degrades to conservative built-in defaults.
    """
    return _MANUAL_COMMAND_LIMITS_CACHE.load()
