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
RUNTIME_LANE_ALIASES_PATH = CONFIG_DIR / 'runtime_lane_aliases.yaml'
FIRMWARE_SEMANTIC_PROFILES_PATH = CONFIG_DIR / 'firmware_semantic_profiles.yaml'
def _resolve_repo_peer_path(*parts: str) -> Path:
    """Resolve a peer project path from either the full repository or a flattened source package."""
    primary = ROOT.parent.joinpath(*parts)
    if primary.exists():
        return primary
    return ROOT.joinpath(*parts)


ESP32_FIRMWARE_PROFILE_HEADER_PATH = _resolve_repo_peer_path('esp32s3_platformio', 'include', 'generated', 'runtime_semantic_profile.hpp')


@dataclass(frozen=True)
class PromotionStatus:
    """Normalized promotion-receipt evaluation.

    Attributes:
        promoted: Whether the runtime tier is currently promoted after resolving
            manual or automatic promotion intent.
        effective: Whether the receipt is eligible to open the public tier after
            metadata and evidence validation.
        missing: Evidence or metadata that prevented the receipt from becoming
            effective. Empty when ``effective`` is true.
        mode: Promotion mode resolved from the authority file.
    """

    promoted: bool
    effective: bool
    missing: tuple[str, ...]
    mode: str = 'manual'


@dataclass(frozen=True)
class ValidatedLiveBackboneStatus:
    """Authoritative validated-live backbone projection."""

    declared: bool
    missing: tuple[str, ...]
    lane_name: str
    planning_backend_profile: str


@dataclass(frozen=True)
class ValidatedLiveReleaseSlice:
    """Normalized validated-live release-slice projection."""

    lane: str
    bringup_launch: str
    target_env_script: str
    target_gate_report: str
    hil_checklist_artifact: str
    release_checklist_artifact: str
    smoke_tests: tuple[str, ...]
    rollback_lane: str


@dataclass(frozen=True)
class RuntimeGovernance:
    """Repository runtime-governance projection.

    Attributes:
        default_runtime_lane: Canonical runtime lane used by operator-facing entrypoints.
        official_product_lines: Product lines allowed in the official delivery track.
        experimental_product_lines: Product lines kept in the experimental track.
        official_runtime_lanes: Runtime lanes that remain part of the official active tree.
        experimental_runtime_lanes: Runtime lanes explicitly isolated as experimental.
        lane_classification: Per-lane delivery-track classification.
    """

    default_runtime_lane: str
    official_product_lines: tuple[str, ...]
    experimental_product_lines: tuple[str, ...]
    official_runtime_lanes: tuple[str, ...]
    experimental_runtime_lanes: tuple[str, ...]
    lane_classification: dict[str, str]


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
    validate_runtime_authority_consistency(payload)
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



def validate_runtime_authority_consistency(authority: dict[str, Any]) -> None:
    """Validate cross-section invariants inside ``runtime_authority.yaml``.

    Args:
        authority: Parsed canonical runtime-authority payload.

    Returns:
        None.

    Raises:
        RuntimeError: Raised when the authority contains internally conflicting
            lane/backbone/backend ownership declarations.

    Boundary behavior:
        The function fails closed. Runtime-generation and validation scripts must
        stop immediately instead of projecting contradictory live-backbone truth
        into launch/runtime contracts.
    """
    if not isinstance(authority, dict):
        raise RuntimeError('runtime authority payload must be a mapping')
    lanes = authority.get('runtime_lanes', {}) if isinstance(authority.get('runtime_lanes'), dict) else {}
    planning_backends = authority.get('planning_backends', {}) if isinstance(authority.get('planning_backends'), dict) else {}
    backbones = authority.get('validated_live_backbones', {}) if isinstance(authority.get('validated_live_backbones'), dict) else {}
    backbone = backbones.get('validated_live', {}) if isinstance(backbones.get('validated_live'), dict) else {}
    if not backbone:
        return
    lane_name = str(backbone.get('lane', 'real_validated_live') or 'real_validated_live').strip()
    if lane_name not in lanes:
        raise RuntimeError(f'validated_live_backbones.validated_live references unknown lane: {lane_name}')
    lane = lanes.get(lane_name, {}) if isinstance(lanes.get(lane_name), dict) else {}
    intended_line = str(lane.get('intended_product_line', lane.get('public_runtime_tier', 'preview')) or 'preview').strip()
    if intended_line != 'validated_live':
        raise RuntimeError('validated_live backbone lane must target intended_product_line=validated_live')
    lane_backbone_name = str(lane.get('validated_live_backbone', '') or '').strip()
    if lane_backbone_name and lane_backbone_name != 'validated_live':
        raise RuntimeError('validated_live backbone lane validated_live_backbone must resolve to validated_live')
    profile_name = str(backbone.get('planning_backend_profile', lane.get('planning_backend_profile', 'validated_live_bridge')) or 'validated_live_bridge').strip()
    if not profile_name:
        raise RuntimeError('validated_live backbone planning_backend_profile must be non-empty')
    if profile_name not in planning_backends:
        raise RuntimeError(f'validated_live backbone references unknown planning backend profile: {profile_name}')
    lane_profile_name = str(lane.get('planning_backend_profile', '') or '').strip()
    if lane_profile_name and lane_profile_name != profile_name:
        raise RuntimeError('validated_live backbone planning_backend_profile must match the bound runtime lane')
    for field_name in ('owner', 'controller_manager_package', 'hardware_interface_package', 'moveit_backend_profile', 'release_gate_profile'):
        if not str(backbone.get(field_name, '') or '').strip():
            raise RuntimeError(f'validated_live backbone missing required field: {field_name}')


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
        planning, execution, vision, ownership, and command-path declarations
        form one coherent authoritative backbone.

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
        'live_owner_declared': bool(str(backbone_config.get('owner', '') or '').strip()),
        'live_controller_manager_package_declared': bool(str(backbone_config.get('controller_manager_package', '') or '').strip()),
        'live_hardware_interface_package_declared': bool(str(backbone_config.get('hardware_interface_package', '') or '').strip()),
        'live_planning_backend_declared': bool(backend.get('declared', False)),
        'ros2_control_execution_backbone_declared': bool(
            _lane_matches('execution_backbone', 'ros2_control')
            and bool(lane.get('execution_backbone_declared', False))
            and _lane_matches('enable_ros2_control', True)
            and _lane_matches('hardware_execution_mode', 'ros2_control_live')
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




def derived_runtime_governance(authority: dict[str, Any]) -> RuntimeGovernance:
    """Return the authoritative runtime-governance projection.

    Args:
        authority: Canonical runtime-authority payload.

    Returns:
        RuntimeGovernance: Normalized delivery-track governance.

    Raises:
        RuntimeError: If governance lists reference unknown lanes or product lines,
            overlap, or leave lanes unclassified.
    """
    if not isinstance(authority, dict):
        raise RuntimeError('runtime authority payload must be a mapping')
    governance = authority.get('runtime_governance', {})
    if not isinstance(governance, dict):
        raise RuntimeError('runtime authority runtime_governance must be a mapping')
    lanes = authority.get('runtime_lanes', {}) if isinstance(authority.get('runtime_lanes'), dict) else {}
    product_lines = authority.get('product_lines', {}) if isinstance(authority.get('product_lines'), dict) else {}

    def _normalize_unique(name: str, values: Any) -> tuple[str, ...]:
        if not isinstance(values, list):
            raise RuntimeError(f'runtime_governance.{name} must be a list')
        normalized = tuple(str(item).strip() for item in values if str(item).strip())
        if len(set(normalized)) != len(normalized):
            raise RuntimeError(f'runtime_governance.{name} must not contain duplicates')
        return normalized

    default_runtime_lane = str(governance.get('default_runtime_lane', 'sim_preview') or 'sim_preview')
    official_product_lines = _normalize_unique('official_product_lines', governance.get('official_product_lines', ['preview', 'validated_sim']))
    experimental_product_lines = _normalize_unique('experimental_product_lines', governance.get('experimental_product_lines', ['validated_live']))
    official_runtime_lanes = _normalize_unique('official_runtime_lanes', governance.get('official_runtime_lanes', list(lanes.keys())))
    experimental_runtime_lanes = _normalize_unique('experimental_runtime_lanes', governance.get('experimental_runtime_lanes', []))

    unknown_product_lines = sorted((set(official_product_lines) | set(experimental_product_lines)) - set(product_lines.keys()))
    if unknown_product_lines:
        raise RuntimeError(f'runtime governance references unknown product lines: {unknown_product_lines}')
    if set(official_product_lines) & set(experimental_product_lines):
        raise RuntimeError('runtime governance product lines must not overlap between official and experimental tracks')

    unknown_lanes = sorted((set(official_runtime_lanes) | set(experimental_runtime_lanes)) - set(lanes.keys()))
    if unknown_lanes:
        raise RuntimeError(f'runtime governance references unknown runtime lanes: {unknown_lanes}')
    if set(official_runtime_lanes) & set(experimental_runtime_lanes):
        raise RuntimeError('runtime governance lanes must not overlap between official and experimental tracks')
    unclassified_lanes = sorted(set(lanes.keys()) - set(official_runtime_lanes) - set(experimental_runtime_lanes))
    if unclassified_lanes:
        raise RuntimeError(f'runtime governance leaves lanes unclassified: {unclassified_lanes}')
    if default_runtime_lane not in official_runtime_lanes:
        raise RuntimeError('runtime governance default_runtime_lane must reference one official runtime lane')

    lane_classification = {lane: 'official_active' for lane in official_runtime_lanes}
    lane_classification.update({lane: 'experimental' for lane in experimental_runtime_lanes})
    return RuntimeGovernance(
        default_runtime_lane=default_runtime_lane,
        official_product_lines=official_product_lines,
        experimental_product_lines=experimental_product_lines,
        official_runtime_lanes=official_runtime_lanes,
        experimental_runtime_lanes=experimental_runtime_lanes,
        lane_classification=lane_classification,
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



def _promotion_mode(receipt: dict[str, Any] | None) -> str:
    payload = receipt if isinstance(receipt, dict) else {}
    mode = str(payload.get('promotion_mode', 'manual') or 'manual').strip().lower()
    return mode if mode in {'manual', 'automatic_when_ready'} else 'manual'


def _automatic_receipt_metadata(marker_payload: dict[str, Any] | None, *, tier_name: str) -> dict[str, str]:
    payload = marker_payload if isinstance(marker_payload, dict) else {}
    generated_at = str(payload.get('auto_checked_at', '') or payload.get('checked_at', '') or 'automatic_when_ready')
    return {
        'receipt_id': str(payload.get('auto_receipt_id', '') or f'{tier_name}-auto-promotion'),
        'checked_by': str(payload.get('auto_checked_by', '') or 'runtime-authority-auto-promoter'),
        'checked_at': generated_at,
    }


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
    mode = _promotion_mode(payload)
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
    promoted = bool(payload.get('promoted', False))
    if mode == 'automatic_when_ready' and not missing:
        promoted = True
    if promoted and mode != 'automatic_when_ready':
        for key in ('receipt_id', 'checked_by', 'checked_at'):
            if not str(payload.get(key, '') or '').strip():
                missing.append(key)
    if promoted and mode == 'automatic_when_ready' and not missing:
        synthesized = _automatic_receipt_metadata(payload, tier_name=str(payload.get('tier_name', 'validated_live') or 'validated_live'))
        for key, value in synthesized.items():
            if not str(value or '').strip():
                missing.append(key)
    return PromotionStatus(promoted=promoted, effective=promoted and not missing, missing=tuple(missing), mode=mode)



def derived_product_lines(authority: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Build product-line exposure as consumed by runtime contract artifacts."""
    product_lines = authority.get('product_lines', {})
    if not isinstance(product_lines, dict):
        raise RuntimeError('runtime authority product_lines must be a mapping')
    governance = derived_runtime_governance(authority)
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
        release_channel = 'official_active' if tier_name in governance.official_product_lines else 'experimental'
        result[tier_name] = {
            'label': str(payload.get('label', tier_name)),
            'description': str(payload.get('description', '')),
            'task_workbench_visible': task_workbench_visible,
            'task_execution_interactive': task_execution_interactive,
            'runtime_badge': str(payload.get('runtime_badge', tier_name.upper())),
            'promotion_controlled': promotion_controlled,
            'promotion_effective': receipt_state.effective,
            'promotion_missing': promotion_missing,
            'release_channel': release_channel,
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
    governance = derived_runtime_governance(authority)
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
        validated_live_lane = intended_tier == 'validated_live' or str(lane.get('validated_live_backbone', '') or '').strip() == 'validated_live'
        if intended_tier == 'validated_live':
            if not (backbone.declared and live_receipt.effective):
                effective_tier = 'preview'
        lane['planning_backend_declared'] = planning_backend_declared
        if validated_live_lane:
            live_backbones = authority.get('validated_live_backbones', {}) if isinstance(authority.get('validated_live_backbones'), dict) else {}
            live_backbone = live_backbones.get('validated_live', {}) if isinstance(live_backbones.get('validated_live'), dict) else {}
            lane['validated_live_backbone_owner'] = str(live_backbone.get('owner', '') or '')
            lane['validated_live_controller_manager_package'] = str(live_backbone.get('controller_manager_package', '') or '')
            lane['validated_live_hardware_interface_package'] = str(live_backbone.get('hardware_interface_package', '') or '')
        else:
            lane['validated_live_backbone_owner'] = ''
            lane['validated_live_controller_manager_package'] = ''
            lane['validated_live_hardware_interface_package'] = ''
        lane['validated_live_backbone_declared'] = backbone.declared if validated_live_lane else False
        lane['validated_live_backbone_missing'] = list(backbone.missing) if validated_live_lane else []
        lane['public_runtime_tier'] = effective_tier
        lane['task_workbench_visible'] = bool(product_lines[effective_tier]['task_workbench_visible'])
        lane['task_execution_interactive'] = bool(product_lines[effective_tier]['task_execution_interactive'])
        lane['runtime_delivery_track'] = governance.lane_classification[str(lane_name)]
        lane['official_runtime_lane'] = bool(str(lane_name) in governance.official_runtime_lanes)
        result[str(lane_name)] = lane
    return result



def derived_validated_live_release_slice(authority: dict[str, Any]) -> dict[str, Any]:
    """Build the validated-live release slice used by launch/runtime/tooling."""
    payload = authority.get('validated_live_release_slice', {})
    if not isinstance(payload, dict):
        raise RuntimeError('runtime authority validated_live_release_slice must be a mapping')
    lane = str(payload.get('lane', 'real_validated_live') or 'real_validated_live').strip()
    if not lane:
        raise RuntimeError('validated_live_release_slice.lane must be non-empty')
    smoke_tests = payload.get('smoke_tests', [])
    if not isinstance(smoke_tests, list) or not all(str(item).strip() for item in smoke_tests):
        raise RuntimeError('validated_live_release_slice.smoke_tests must be a non-empty list of test ids')
    normalized_smoke_tests = [str(item).strip() for item in smoke_tests if str(item).strip()]
    missing = [item for item in normalized_smoke_tests if not (ROOT / item).exists()]
    if missing:
        raise RuntimeError(f'validated_live_release_slice.smoke_tests reference missing paths: {', '.join(missing)}')
    return {
        'lane': lane,
        'bringup_launch': str(payload.get('bringup_launch', '') or ''),
        'target_env_script': str(payload.get('target_env_script', '') or ''),
        'target_gate_report': str(payload.get('target_gate_report', '') or ''),
        'hil_checklist_artifact': str(payload.get('hil_checklist_artifact', '') or ''),
        'release_checklist_artifact': str(payload.get('release_checklist_artifact', '') or ''),
        'smoke_tests': normalized_smoke_tests,
        'rollback_lane': str(payload.get('rollback_lane', 'sim_authoritative') or 'sim_authoritative'),
    }


def _build_task_graph(*, template_id: str, sequence_mode: str, plugin_key: str, preconditions: list[str]) -> dict[str, Any]:
    """Return one normalized task-graph contract for a template.

    The graph is intentionally declarative: templates still choose the graph,
    while runtime execution can progressively migrate from plugin dispatch to
    graph-aware orchestration without breaking API payloads.
    """
    normalized_mode = str(sequence_mode or 'single_target').strip() or 'single_target'
    normalized_plugin = str(plugin_key or normalized_mode).strip() or normalized_mode
    base_nodes = [
        {'id': 'perception', 'kind': 'perception', 'stage': 'perception', 'label': '目标确认', 'terminal': False},
        {'id': 'plan', 'kind': 'planning', 'stage': 'planning', 'label': '轨迹规划', 'terminal': False},
        {'id': 'execute', 'kind': 'execution', 'stage': 'execution', 'label': '执行', 'terminal': False},
        {'id': 'verify', 'kind': 'verification', 'stage': 'verification', 'label': '结果校验', 'terminal': True},
    ]
    base_edges = [
        {'from': 'perception', 'to': 'plan', 'condition': 'target_locked'},
        {'from': 'plan', 'to': 'execute', 'condition': 'plan_ready'},
        {'from': 'execute', 'to': 'verify', 'condition': 'execution_done'},
    ]
    recovery = {'mode': 'retry_once_then_fail_closed', 'maxAutomaticRetry': 1, 'maxRetries': 2}
    if normalized_mode == 'selector_routed':
        base_nodes.insert(1, {'id': 'selector', 'kind': 'selection', 'stage': 'selection', 'label': '目标类别路由', 'terminal': False})
        base_edges = [
            {'from': 'perception', 'to': 'selector', 'condition': 'target_locked'},
            {'from': 'selector', 'to': 'plan', 'condition': 'selector_resolved'},
            {'from': 'plan', 'to': 'execute', 'condition': 'plan_ready'},
            {'from': 'execute', 'to': 'verify', 'condition': 'execution_done'},
        ]
        recovery = {'mode': 'selector_retarget_then_fail_closed', 'maxAutomaticRetry': 1, 'maxRetries': 2}
    elif normalized_mode == 'continuous':
        base_nodes = [
            {'id': 'perception', 'kind': 'perception', 'stage': 'perception', 'label': '目标扫描', 'terminal': False},
            {'id': 'plan', 'kind': 'planning', 'stage': 'planning', 'label': '批次规划', 'terminal': False},
            {'id': 'execute_batch', 'kind': 'execution', 'stage': 'execution', 'label': '批次执行', 'terminal': False},
            {'id': 'verify_batch', 'kind': 'verification', 'stage': 'verification', 'label': '批次校验', 'terminal': False},
            {'id': 'complete', 'kind': 'terminal', 'stage': 'terminal', 'label': '完成', 'terminal': True},
        ]
        base_edges = [
            {'from': 'perception', 'to': 'plan', 'condition': 'next_target_available'},
            {'from': 'plan', 'to': 'execute_batch', 'condition': 'plan_ready'},
            {'from': 'execute_batch', 'to': 'verify_batch', 'condition': 'execution_done'},
            {'from': 'verify_batch', 'to': 'perception', 'condition': 'targets_remaining'},
            {'from': 'verify_batch', 'to': 'complete', 'condition': 'workspace_clear'},
        ]
        recovery = {'mode': 'batch_continue_with_failure_ledger', 'maxAutomaticRetry': 1, 'maxRetries': 2}
    return {
        'graphKey': template_id,
        'entryNode': base_nodes[0]['id'],
        'sequenceMode': normalized_mode,
        'pluginKey': normalized_plugin,
        'preconditions': [str(item) for item in preconditions if str(item).strip()],
        'nodes': base_nodes,
        'edges': base_edges,
        'recoveryPolicy': recovery,
        'recovery': recovery,
        'auditSurface': ['perception', 'plan', 'execute', 'verify'],
        'graphVersion': 'v1',
        'templateId': template_id,
    }


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
        sequence_mode = str(item.get('sequence_mode', 'single_target') or 'single_target')
        plugin_key = str(item.get('plugin_key', item.get('sequence_mode', 'single_target')) or 'single_target')
        preconditions = [str(value) for value in item.get('preconditions', []) if str(value).strip()]
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
            'capability_tags': [str(value) for value in item.get('capability_tags', []) if str(value).strip()],
            'preconditions': preconditions,
            'sequence_mode': sequence_mode,
            'plugin_key': plugin_key,
            'graph_key': template_id,
            'task_graph': _build_task_graph(template_id=template_id, sequence_mode=sequence_mode, plugin_key=plugin_key, preconditions=preconditions),
        })
    return {
        'schema_version': int(authority.get('schema_version', 1) or 1),
        'product_lines': {
            key: {
                'label': value['label'],
                'description': value['description'],
                'task_workbench_visible': bool(value['task_workbench_visible']),
                'task_execution_interactive': bool(value['task_execution_interactive']),
                'release_channel': str(value.get('release_channel', 'official_active')),
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
        item_with_name = dict(item)
        item_with_name.setdefault('tier_name', str(name))
        status = evaluate_promotion_receipt(item_with_name, authority=authority, evidence_manifest=evidence_manifest)
        receipt_id = str(item.get('receipt_id', '') or '')
        checked_by = str(item.get('checked_by', '') or '')
        checked_at = str(item.get('checked_at', '') or '')
        if status.mode == 'automatic_when_ready' and status.promoted and status.effective:
            synthesized = _automatic_receipt_metadata(item_with_name, tier_name=str(name))
            receipt_id = synthesized['receipt_id']
            checked_by = synthesized['checked_by']
            checked_at = synthesized['checked_at']
        result[str(name)] = {
            'promotion_mode': status.mode,
            'promoted': bool(status.promoted),
            'receipt_id': receipt_id,
            'checked_by': checked_by,
            'checked_at': checked_at,
            'required_evidence': [str(value) for value in item.get('required_evidence', []) if str(value).strip()],
            'evidence': [str(value) for value in item.get('evidence', []) if str(value).strip()],
            'reason': str(item.get('reason', '') or ''),
            'effective': bool(status.effective),
            'missing_evidence': list(status.missing),
            'auto_generated': bool(status.mode == 'automatic_when_ready' and status.promoted and status.effective),
        }
    return result




def derived_runtime_lane_aliases(authority: dict[str, Any]) -> dict[str, Any]:
    """Build canonical runtime-lane alias metadata from the authority file.

    Args:
        authority: Canonical runtime-authority payload.

    Returns:
        A structured alias manifest grouped by lifecycle plus flattened maps used
        by launch-time resolution and contract generation.

    Raises:
        RuntimeError: When alias groups or referenced lanes are invalid.
    """
    payload = authority.get('runtime_lane_aliases', {})
    if not isinstance(payload, dict):
        raise RuntimeError('runtime authority runtime_lane_aliases must be a mapping')
    lanes = authority.get('runtime_lanes', {}) if isinstance(authority.get('runtime_lanes'), dict) else {}
    governance = derived_runtime_governance(authority)
    known_lanes = set(lanes.keys())

    def _normalize_group(group_name: str) -> dict[str, dict[str, Any]]:
        group = payload.get(group_name, {})
        if not isinstance(group, dict):
            raise RuntimeError(f'runtime_lane_aliases.{group_name} must be a mapping')
        normalized: dict[str, dict[str, Any]] = {}
        for alias, item in group.items():
            alias_name = str(alias).strip().lower()
            if not alias_name:
                raise RuntimeError(f'runtime_lane_aliases.{group_name} contains an empty alias key')
            if alias_name in normalized:
                raise RuntimeError(f'runtime_lane_aliases.{group_name} contains duplicate alias: {alias_name}')
            if not isinstance(item, dict):
                raise RuntimeError(f'runtime_lane_aliases.{group_name}.{alias_name} must be a mapping')
            lane = str(item.get('lane', '') or '').strip()
            if lane not in known_lanes:
                raise RuntimeError(f'runtime_lane_aliases.{group_name}.{alias_name} references unknown lane: {lane}')
            release_track = str(item.get('release_track', governance.lane_classification.get(lane, 'experimental')) or governance.lane_classification.get(lane, 'experimental')).strip()
            lifecycle = str(item.get('lifecycle', group_name) or group_name).strip()
            normalized[alias_name] = {
                'lane': lane,
                'release_track': release_track,
                'lifecycle': lifecycle,
            }
            for optional_key in ('replacement', 'retirement_phase'):
                optional_value = str(item.get(optional_key, '') or '').strip()
                if optional_value:
                    normalized[alias_name][optional_key] = optional_value
        return normalized

    compatibility = _normalize_group('compatibility')
    experimental = _normalize_group('experimental')
    retired = _normalize_group('retired')
    duplicates = (set(compatibility) & set(experimental)) | (set(compatibility) & set(retired)) | (set(experimental) & set(retired))
    if duplicates:
        raise RuntimeError(f'runtime lane aliases must be unique across lifecycle groups: {sorted(duplicates)}')
    return {
        'schema_version': int(authority.get('schema_version', 1) or 1),
        'compatibility': compatibility,
        'experimental': experimental,
        'retired': retired,
        'resolved': {
            'active': {**{alias: item['lane'] for alias, item in compatibility.items()}, **{alias: item['lane'] for alias, item in experimental.items()}},
            'compatibility': {alias: item['lane'] for alias, item in compatibility.items()},
            'experimental': {alias: item['lane'] for alias, item in experimental.items()},
            'retired': {alias: item['lane'] for alias, item in retired.items()},
        },
    }


def derived_firmware_semantic_profiles(authority: dict[str, Any]) -> dict[str, Any]:
    """Build authoritative firmware semantic profiles mirrored from runtime authority."""
    payload = authority.get('firmware_semantic_profiles', {})
    if not isinstance(payload, dict):
        raise RuntimeError('runtime authority firmware_semantic_profiles must be a mapping')
    lanes = authority.get('runtime_lanes', {}) if isinstance(authority.get('runtime_lanes'), dict) else {}
    esp32_payload = payload.get('esp32', {}) if isinstance(payload.get('esp32'), dict) else {}
    default_profile = str(esp32_payload.get('default_profile', '') or '').strip()
    profile_payload = esp32_payload.get('profiles', {}) if isinstance(esp32_payload.get('profiles'), dict) else {}
    normalized_profiles: dict[str, dict[str, Any]] = {}
    for name, item in profile_payload.items():
        profile_name = str(name).strip()
        if not profile_name:
            raise RuntimeError('firmware_semantic_profiles.esp32.profiles contains an empty profile name')
        if not isinstance(item, dict):
            raise RuntimeError(f'firmware_semantic_profiles.esp32.profiles.{profile_name} must be a mapping')
        source_lane = str(item.get('source_lane', '') or '').strip()
        if source_lane and source_lane not in lanes:
            raise RuntimeError(f'firmware semantic profile {profile_name} references unknown runtime lane: {source_lane}')
        normalized_profiles[profile_name] = {
            'source_lane': source_lane,
            'camera_available': bool(item.get('camera_available', False)),
            'frame_ingress_live': bool(item.get('frame_ingress_live', False)),
            'stream_semantic': str(item.get('stream_semantic', 'reserved') or 'reserved'),
            'frame_ingress_mode': str(item.get('frame_ingress_mode', 'reserved_endpoint') or 'reserved_endpoint'),
            'stream_delivery_model': str(item.get('stream_delivery_model', 'control_plane_only') or 'control_plane_only'),
            'stream_control_plane': str(item.get('stream_control_plane', 'esp32_metadata_bridge') or 'esp32_metadata_bridge'),
            'stream_message': str(item.get('stream_message', '') or ''),
            'hostname': str(item.get('hostname', 'esp32.local') or 'esp32.local'),
        }
    if default_profile not in normalized_profiles:
        raise RuntimeError('firmware_semantic_profiles.esp32.default_profile must reference one declared profile')
    return {
        'schema_version': int(authority.get('schema_version', 1) or 1),
        'esp32': {
            'default_profile': default_profile,
            'profiles': normalized_profiles,
        },
    }


def render_esp32_runtime_semantic_header(authority: dict[str, Any], *, header: str) -> str:
    """Render the generated ESP32 semantic-profile header from runtime authority."""
    profiles_payload = derived_firmware_semantic_profiles(authority)
    esp32 = profiles_payload['esp32']
    profiles = esp32['profiles']
    default_profile = str(esp32['default_profile'])

    def _macro_name(profile_name: str) -> str:
        return profile_name.upper()

    def _cpp_bool(value: bool) -> str:
        return '1' if value else '0'

    lines = [header.rstrip(), '#pragma once', '', '// Generated from runtime_authority.yaml. Do not edit manually.', '']
    for index, profile_name in enumerate(profiles.keys(), start=1):
        lines.append(f'#define EMBODIED_ARM_RUNTIME_SEMANTIC_PROFILE_{_macro_name(profile_name)} {index}')
    lines.append('')
    lines.append('#ifndef EMBODIED_ARM_RUNTIME_SEMANTIC_PROFILE')
    lines.append(f'#define EMBODIED_ARM_RUNTIME_SEMANTIC_PROFILE EMBODIED_ARM_RUNTIME_SEMANTIC_PROFILE_{_macro_name(default_profile)}')
    lines.append('#endif')
    lines.append('')
    first = True
    for profile_name, item in profiles.items():
        if first:
            lines.append(f'#if EMBODIED_ARM_RUNTIME_SEMANTIC_PROFILE == EMBODIED_ARM_RUNTIME_SEMANTIC_PROFILE_{_macro_name(profile_name)}')
            first = False
        else:
            lines.append(f'#elif EMBODIED_ARM_RUNTIME_SEMANTIC_PROFILE == EMBODIED_ARM_RUNTIME_SEMANTIC_PROFILE_{_macro_name(profile_name)}')
        lines.append(f'#define EMBODIED_ARM_RUNTIME_SEMANTIC_PROFILE_NAME "{profile_name}"')
        lines.append(f'#define EMBODIED_ARM_DEFAULT_CAMERA_AVAILABLE {_cpp_bool(bool(item["camera_available"]))}')
        lines.append(f'#define EMBODIED_ARM_DEFAULT_FRAME_INGRESS_LIVE {_cpp_bool(bool(item["frame_ingress_live"]))}')
        lines.append(f'#define EMBODIED_ARM_DEFAULT_STREAM_SEMANTIC "{item["stream_semantic"]}"')
        lines.append(f'#define EMBODIED_ARM_DEFAULT_FRAME_INGRESS_MODE "{item["frame_ingress_mode"]}"')
        lines.append(f'#define EMBODIED_ARM_DEFAULT_STREAM_DELIVERY_MODEL "{item["stream_delivery_model"]}"')
        stream_message = str(item["stream_message"] or '').replace('\\', r'\\').replace('\"', r'\\"')
        lines.append(f'#define EMBODIED_ARM_DEFAULT_STREAM_CONTROL_PLANE "{item["stream_control_plane"]}"')
        lines.append(f'#define EMBODIED_ARM_DEFAULT_STREAM_MESSAGE "{stream_message}"')
        lines.append(f'#define EMBODIED_ARM_DEFAULT_HOSTNAME "{item["hostname"]}"')
        lines.append(f'#define EMBODIED_ARM_DEFAULT_SOURCE_LANE "{item["source_lane"]}"')
    lines.append('#else')
    lines.append('#error "Unsupported EMBODIED_ARM_RUNTIME_SEMANTIC_PROFILE selection"')
    lines.append('#endif')
    lines.append('')
    return '\n'.join(lines) + '\n'

def render_yaml_with_header(payload: dict[str, Any], *, header: str) -> str:
    """Render one YAML document with a leading comment header."""
    return f'{header.rstrip()}\n' + yaml.safe_dump(payload, sort_keys=False, allow_unicode=True)
