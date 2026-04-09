from __future__ import annotations

"""Canonical runtime-authority helpers shared by generation and validation scripts.

The runtime authority file is the single editable source for runtime lanes,
planning backends, promotion receipts, release-gate prerequisites, product-line
exposure, and task catalog metadata. Derived YAML files consumed by the runtime
are generated from this source so Gateway, frontend contract artifacts, and ROS
launch configuration do not drift independently.
"""

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent
RUNTIME_AUTHORITY_PATH = ROOT / 'backend' / 'embodied_arm_ws' / 'src' / 'arm_bringup' / 'config' / 'runtime_authority.yaml'
CONFIG_DIR = RUNTIME_AUTHORITY_PATH.parent
RUNTIME_PROFILES_PATH = CONFIG_DIR / 'runtime_profiles.yaml'
PLANNING_BACKEND_PROFILES_PATH = CONFIG_DIR / 'planning_backend_profiles.yaml'
RUNTIME_PROMOTION_RECEIPTS_PATH = CONFIG_DIR / 'runtime_promotion_receipts.yaml'
TASK_CAPABILITY_MANIFEST_PATH = CONFIG_DIR / 'task_capability_manifest.yaml'
PLACEMENT_PROFILES_PATH = CONFIG_DIR / 'placement_profiles.yaml'
VALIDATED_LIVE_EVIDENCE_PATH = CONFIG_DIR / 'validated_live_evidence.yaml'
RELEASE_GATE_REPORT_PATH = ROOT / 'artifacts' / 'release_gates' / 'target_runtime_gate.json'


@dataclass(frozen=True)
class PromotionStatus:
    """Normalized promotion-receipt evaluation.

    Attributes:
        promoted: Raw requested promotion state from the authority file.
        effective: Whether the receipt is eligible to open the public tier after
            metadata and evidence validation.
        missing: Evidence or metadata that prevented the receipt from becoming
            effective. Empty when ``effective`` is true.
    """

    promoted: bool
    effective: bool
    missing: tuple[str, ...]


@dataclass(frozen=True)
class ValidatedLiveBackboneStatus:
    """Authoritative validated-live backbone projection."""

    declared: bool
    missing: tuple[str, ...]
    lane_name: str
    planning_backend_profile: str



def load_runtime_authority(path: Path | None = None) -> dict[str, Any]:
    """Load the canonical runtime-authority YAML.

    Args:
        path: Optional override path used by tests or offline tooling.

    Returns:
        Parsed authority payload as a dictionary.

    Raises:
        RuntimeError: If the YAML is unreadable or does not contain a mapping.
    """
    authority_path = path or RUNTIME_AUTHORITY_PATH
    try:
        payload = yaml.safe_load(authority_path.read_text(encoding='utf-8')) or {}
    except Exception as exc:  # pragma: no cover - surfaced through callers/tests
        raise RuntimeError(f'failed to load runtime authority: {authority_path}: {exc}') from exc
    if not isinstance(payload, dict):
        raise RuntimeError(f'runtime authority must be a mapping: {authority_path}')
    return payload



def known_place_profiles(path: Path | None = None) -> set[str]:
    """Return all authoritative placement profile names.

    Boundary behavior:
        Missing or invalid placement profile files produce an empty set so the
        caller can emit a deterministic validation error.
    """
    profile_path = path or PLACEMENT_PROFILES_PATH
    try:
        payload = yaml.safe_load(profile_path.read_text(encoding='utf-8')) or {}
    except Exception:
        return set()
    if not isinstance(payload, dict):
        return set()
    profiles = payload.get('place_profiles', payload)
    if not isinstance(profiles, dict):
        return set()
    return {str(name) for name in profiles.keys()}



def load_validated_live_evidence(path: Path | None = None) -> dict[str, Any]:
    """Load validated-live evidence status declarations.

    Boundary behavior:
        Missing or invalid files fail closed by returning an empty evidence mapping.
    """
    evidence_path = path or VALIDATED_LIVE_EVIDENCE_PATH
    try:
        payload = yaml.safe_load(evidence_path.read_text(encoding='utf-8')) or {}
    except Exception:
        return {'schema_version': 1, 'evidence': {}}
    if not isinstance(payload, dict):
        return {'schema_version': 1, 'evidence': {}}
    evidence = payload.get('evidence', {})
    if not isinstance(evidence, dict):
        evidence = {}
    return {'schema_version': int(payload.get('schema_version', 1) or 1), 'evidence': evidence}



def effective_target_runtime_gate_path(path: Path | None = None) -> Path:
    """Return the effective target-runtime gate report path.

    Environment override:
        EMBODIED_ARM_TARGET_RUNTIME_GATE_FILE
    """
    env_path = __import__('os').environ.get('EMBODIED_ARM_TARGET_RUNTIME_GATE_FILE', '').strip()
    if env_path:
        return Path(env_path).expanduser()
    return path or RELEASE_GATE_REPORT_PATH



def load_release_gate_report(path: Path | None = None) -> dict[str, Any]:
    """Load the machine-readable target-runtime release gate report.

    Boundary behavior:
        Missing or invalid files fail closed by returning an empty mapping.
    """
    report_path = effective_target_runtime_gate_path(path)
    try:
        payload = json.loads(report_path.read_text(encoding='utf-8')) if report_path.exists() else {}
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}



def _marker_in_receipt(receipt: dict[str, Any], marker: str) -> bool:
    return marker in {str(item).strip() for item in receipt.get('evidence', []) if str(item).strip()}



def validated_live_backbone_status(authority: dict[str, Any] | None = None) -> ValidatedLiveBackboneStatus:
    """Return validated-live backbone readiness derived from the canonical authority.

    Args:
        authority: Optional preloaded runtime-authority payload.

    Returns:
        ValidatedLiveBackboneStatus describing whether the configured live
        planning, execution, vision, and command-path declarations form one
        coherent authoritative backbone.

    Raises:
        Does not raise. Invalid payloads fail closed.
    """
    payload = authority if isinstance(authority, dict) else load_runtime_authority()
    lanes = payload.get('runtime_lanes', {}) if isinstance(payload.get('runtime_lanes'), dict) else {}
    backends = payload.get('planning_backends', {}) if isinstance(payload.get('planning_backends'), dict) else {}
    backbones = payload.get('validated_live_backbones', {}) if isinstance(payload.get('validated_live_backbones'), dict) else {}
    backbone_config = backbones.get('validated_live', {}) if isinstance(backbones.get('validated_live'), dict) else {}
    lane_name = str(backbone_config.get('lane', 'real_validated_live') or 'real_validated_live')
    lane = lanes.get(lane_name, {}) if isinstance(lanes.get(lane_name), dict) else {}
    profile_name = str(backbone_config.get('planning_backend_profile', lane.get('planning_backend_profile', 'validated_live_bridge')) or 'validated_live_bridge')
    backend = backends.get(profile_name, {}) if isinstance(backends.get(profile_name), dict) else {}
    requirements = backbone_config.get('requirements', {}) if isinstance(backbone_config.get('requirements'), dict) else {}

    def _lane_matches(field: str, default: Any) -> bool:
        expected = requirements.get(field, default)
        actual = lane.get(field, default)
        return actual == expected

    checks = {
        'live_planning_backend_declared': bool(backend.get('declared', False)),
        'ros2_control_execution_backbone_declared': bool(
            _lane_matches('execution_backbone', 'ros2_control')
            and _lane_matches('execution_backbone_declared', True)
            and _lane_matches('enable_ros2_control', True)
        ),
        'live_vision_backbone_declared': bool(
            _lane_matches('camera_source', 'topic')
            and _lane_matches('esp32_frame_ingress_live', True)
            and _lane_matches('frame_ingress_mode', 'live_camera_stream')
            and _lane_matches('scene_provider_mode', 'runtime_service')
            and _lane_matches('grasp_provider_mode', 'runtime_service')
        ),
        'live_hardware_command_path_declared': bool(_lane_matches('forward_hardware_commands', True)),
    }
    missing = tuple(name for name, ok in checks.items() if not ok)
    return ValidatedLiveBackboneStatus(
        declared=not missing,
        missing=missing,
        lane_name=lane_name,
        planning_backend_profile=profile_name,
    )



def _validated_live_artifact_passed(marker: str, evidence_manifest: dict[str, Any] | None) -> bool:
    payload = evidence_manifest if isinstance(evidence_manifest, dict) else {'evidence': {}}
    evidence = payload.get('evidence', {}) if isinstance(payload.get('evidence'), dict) else {}
    item = evidence.get(marker, {}) if isinstance(evidence.get(marker), dict) else {}
    if str(item.get('status', '') or '').strip().lower() != 'passed':
        return False
    artifact = str(item.get('artifact', '') or '').strip()
    if not artifact or not (ROOT / artifact).exists():
        return False
    gate_field = str(item.get('gate_field', '') or '').strip()
    if gate_field:
        report_path_value = str(item.get('gate_report', '') or '').strip()
        report = load_release_gate_report(ROOT / report_path_value) if report_path_value else load_release_gate_report()
        if str(report.get(gate_field, '') or '').strip().lower() != 'passed':
            return False
    return True



def _required_evidence_satisfied(marker: str, authority: dict[str, Any] | None, evidence_manifest: dict[str, Any] | None) -> bool:
    backbone = validated_live_backbone_status(authority or {})
    if marker == 'validated_live_backbone_declared':
        return backbone.declared
    if marker == 'live_planning_backend_declared':
        return 'live_planning_backend_declared' not in backbone.missing
    if marker == 'ros2_control_execution_backbone_declared':
        return 'ros2_control_execution_backbone_declared' not in backbone.missing
    if marker == 'live_vision_backbone_declared':
        return 'live_vision_backbone_declared' not in backbone.missing
    if marker == 'live_hardware_command_path_declared':
        return 'live_hardware_command_path_declared' not in backbone.missing
    if marker in {'target_runtime_gate_passed', 'hil_gate_passed', 'release_checklist_signed', 'hil_smoke_passed'}:
        return _validated_live_artifact_passed(marker, evidence_manifest)
    return True


def evaluate_promotion_receipt(
    receipt: dict[str, Any] | None,
    *,
    authority: dict[str, Any] | None = None,
    evidence_manifest: dict[str, Any] | None = None,
) -> PromotionStatus:
    """Evaluate one runtime promotion receipt.

    Args:
        receipt: Raw receipt mapping from ``promotion_tiers``.
        authority: Optional runtime-authority payload used to validate dynamic
            prerequisites such as declared live backbone readiness.
        evidence_manifest: Optional validated-live evidence manifest used to
            require repository-tracked target-runtime evidence before promotion.

    Returns:
        PromotionStatus describing raw promotion intent, effective promotion
        state, and any missing metadata/evidence.

    Raises:
        Does not raise. Missing or malformed payloads fail closed.
    """
    payload = receipt if isinstance(receipt, dict) else {}
    promoted = bool(payload.get('promoted', False))
    missing: list[str] = []
    for item in payload.get('required_evidence', []):
        marker = str(item).strip()
        if not marker:
            continue
        if not _marker_in_receipt(payload, marker):
            missing.append(marker)
            continue
        if not _required_evidence_satisfied(marker, authority, evidence_manifest):
            missing.append(marker)
    if promoted:
        for key in ('receipt_id', 'checked_by', 'checked_at'):
            if not str(payload.get(key, '') or '').strip():
                missing.append(key)
    return PromotionStatus(promoted=promoted, effective=promoted and not missing, missing=tuple(missing))



def derived_product_lines(authority: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Build product-line exposure as consumed by runtime contract artifacts."""
    product_lines = authority.get('product_lines', {})
    if not isinstance(product_lines, dict):
        raise RuntimeError('runtime authority product_lines must be a mapping')
    receipts = authority.get('promotion_tiers', {}) if isinstance(authority.get('promotion_tiers'), dict) else {}
    evidence_manifest = load_validated_live_evidence()
    backbone = validated_live_backbone_status(authority)
    result: dict[str, dict[str, Any]] = {}
    for tier_name in ('preview', 'validated_sim', 'validated_live'):
        payload = product_lines.get(tier_name, {}) if isinstance(product_lines.get(tier_name), dict) else {}
        promotion_controlled = bool(payload.get('promotion_controlled', False))
        receipt_state = evaluate_promotion_receipt(
            receipts.get(tier_name, {}) if isinstance(receipts, dict) else {},
            authority=authority,
            evidence_manifest=evidence_manifest,
        )
        promotion_missing = list(receipt_state.missing)
        if tier_name == 'validated_live' and not backbone.declared and 'validated_live_backbone_declared' not in promotion_missing:
            promotion_missing.append('validated_live_backbone_declared')
        if promotion_controlled and not receipt_state.effective:
            task_workbench_visible = bool(payload.get('fail_closed_task_workbench_visible', False))
            task_execution_interactive = bool(payload.get('fail_closed_task_execution_interactive', False))
        else:
            task_workbench_visible = bool(payload.get('task_workbench_visible', tier_name != 'preview'))
            task_execution_interactive = bool(payload.get('task_execution_interactive', tier_name != 'preview'))
        result[tier_name] = {
            'label': str(payload.get('label', tier_name)),
            'description': str(payload.get('description', '')),
            'task_workbench_visible': task_workbench_visible,
            'task_execution_interactive': task_execution_interactive,
            'runtime_badge': str(payload.get('runtime_badge', tier_name.upper())),
            'promotion_controlled': promotion_controlled,
            'promotion_effective': receipt_state.effective,
            'promotion_missing': promotion_missing,
        }
    return result



def derived_planning_backends(authority: dict[str, Any]) -> dict[str, dict[str, Any]]:
    payload = authority.get('planning_backends', {})
    if not isinstance(payload, dict):
        raise RuntimeError('runtime authority planning_backends must be a mapping')
    result: dict[str, dict[str, Any]] = {}
    for name, item in payload.items():
        if not isinstance(item, dict):
            raise RuntimeError(f'planning backend {name} must be a mapping')
        result[str(name)] = dict(item)
    return result



def derived_runtime_lanes(authority: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Build runtime-lane profiles consumed by ROS launch and gateway projections."""
    lanes = authority.get('runtime_lanes', {})
    if not isinstance(lanes, dict):
        raise RuntimeError('runtime authority runtime_lanes must be a mapping')
    product_lines = derived_product_lines(authority)
    planning_backends = derived_planning_backends(authority)
    receipts = authority.get('promotion_tiers', {}) if isinstance(authority.get('promotion_tiers'), dict) else {}
    evidence_manifest = load_validated_live_evidence()
    live_receipt = evaluate_promotion_receipt(
        receipts.get('validated_live', {}),
        authority=authority,
        evidence_manifest=evidence_manifest,
    )
    backbone = validated_live_backbone_status(authority)
    result: dict[str, dict[str, Any]] = {}
    for lane_name, item in lanes.items():
        if not isinstance(item, dict):
            raise RuntimeError(f'runtime lane {lane_name} must be a mapping')
        lane = dict(item)
        intended_tier = str(lane.pop('intended_product_line', lane.get('public_runtime_tier', 'preview')) or 'preview')
        if intended_tier not in product_lines:
            raise RuntimeError(f'runtime lane {lane_name} references unknown product line: {intended_tier}')
        planning_backend_profile = str(lane.get('planning_backend_profile', '') or '').strip()
        if planning_backend_profile and planning_backend_profile not in planning_backends:
            raise RuntimeError(f'runtime lane {lane_name} references unknown planning backend profile: {planning_backend_profile}')
        planning_backend_declared = bool(planning_backends.get(planning_backend_profile, {}).get('declared', True)) if planning_backend_profile else bool(lane.get('planning_backend_declared', True))
        effective_tier = intended_tier
        if intended_tier == 'validated_live':
            if not (backbone.declared and live_receipt.effective):
                effective_tier = 'preview'
        lane['planning_backend_declared'] = planning_backend_declared
        lane['validated_live_backbone_declared'] = backbone.declared if intended_tier == 'validated_live' else False
        lane['validated_live_backbone_missing'] = list(backbone.missing) if intended_tier == 'validated_live' else []
        lane['public_runtime_tier'] = effective_tier
        lane['task_workbench_visible'] = bool(product_lines[effective_tier]['task_workbench_visible'])
        lane['task_execution_interactive'] = bool(product_lines[effective_tier]['task_execution_interactive'])
        result[str(lane_name)] = lane
    return result



def derived_task_manifest(authority: dict[str, Any]) -> dict[str, Any]:
    templates = authority.get('task_templates', [])
    if not isinstance(templates, list):
        raise RuntimeError('runtime authority task_templates must be a list')
    place_profiles = known_place_profiles()
    product_lines = derived_product_lines(authority)
    normalized_templates: list[dict[str, Any]] = []
    for index, item in enumerate(templates):
        if not isinstance(item, dict):
            raise RuntimeError(f'task template at index {index} must be a mapping')
        template_id = str(item.get('id', '') or '').strip()
        if not template_id:
            raise RuntimeError('task template id must be non-empty')
        required_runtime_tier = str(item.get('required_runtime_tier', 'validated_sim') or 'validated_sim')
        if required_runtime_tier not in product_lines:
            raise RuntimeError(f'task template {template_id} references unknown runtime tier: {required_runtime_tier}')
        resolved_profiles = item.get('resolved_place_profiles', {}) if isinstance(item.get('resolved_place_profiles'), dict) else {}
        for selector, profile_name in resolved_profiles.items():
            profile_value = str(profile_name or '').strip()
            if profile_value and profile_value not in place_profiles:
                raise RuntimeError(f'task template {template_id} references unknown place profile {profile_value} for selector {selector}')
        normalized_templates.append({
            'id': template_id,
            'name': str(item.get('name', template_id)),
            'description': str(item.get('description', '')),
            'frontend_task_type': str(item.get('frontend_task_type', 'pick_place')),
            'backend_task_type': str(item.get('backend_task_type', 'PICK_AND_PLACE')),
            'task_profile_path': str(item.get('task_profile_path', '') or ''),
            'default_target_category': item.get('default_target_category', None),
            'allowed_target_categories': [str(value) for value in item.get('allowed_target_categories', []) if str(value).strip()],
            'resolved_place_profiles': {str(key): str(value) for key, value in resolved_profiles.items()},
            'risk_level': str(item.get('risk_level', 'medium')),
            'required_runtime_tier': required_runtime_tier,
            'operator_hint': str(item.get('operator_hint', '')),
        })
    return {
        'schema_version': int(authority.get('schema_version', 1) or 1),
        'product_lines': {
            key: {
                'label': value['label'],
                'description': value['description'],
                'task_workbench_visible': bool(value['task_workbench_visible']),
                'task_execution_interactive': bool(value['task_execution_interactive']),
            }
            for key, value in derived_product_lines(authority).items()
        },
        'templates': normalized_templates,
    }



def derived_promotion_receipts(authority: dict[str, Any]) -> dict[str, dict[str, Any]]:
    payload = authority.get('promotion_tiers', {})
    if not isinstance(payload, dict):
        raise RuntimeError('runtime authority promotion_tiers must be a mapping')
    evidence_manifest = load_validated_live_evidence()
    result: dict[str, dict[str, Any]] = {}
    for name, item in payload.items():
        if not isinstance(item, dict):
            raise RuntimeError(f'promotion tier {name} must be a mapping')
        status = evaluate_promotion_receipt(item, authority=authority, evidence_manifest=evidence_manifest)
        result[str(name)] = {
            'promoted': bool(item.get('promoted', False)),
            'receipt_id': str(item.get('receipt_id', '') or ''),
            'checked_by': str(item.get('checked_by', '') or ''),
            'checked_at': str(item.get('checked_at', '') or ''),
            'required_evidence': [str(value) for value in item.get('required_evidence', []) if str(value).strip()],
            'evidence': [str(value) for value in item.get('evidence', []) if str(value).strip()],
            'reason': str(item.get('reason', '') or ''),
            'effective': bool(status.effective),
            'missing_evidence': list(status.missing),
        }
    return result



def render_yaml_with_header(payload: dict[str, Any], *, header: str) -> str:
    """Render one YAML document with a leading comment header."""
    return f'{header.rstrip()}\n' + yaml.safe_dump(payload, sort_keys=False, allow_unicode=True)
