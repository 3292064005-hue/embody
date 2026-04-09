from __future__ import annotations

import argparse
import ast
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

if str(Path(__file__).resolve().parents[1]) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from runtime_authority import derived_product_lines, derived_promotion_receipts, derived_runtime_lanes, derived_task_manifest, load_runtime_authority

ROOT = Path(__file__).resolve().parents[1]
BACKEND_SRC = ROOT / 'backend' / 'embodied_arm_ws' / 'src'
DOCS = ROOT / 'docs'
DOCS_GENERATED = DOCS / 'generated'
JSON_PATH = DOCS_GENERATED / 'runtime_contract_manifest.json'
MD_PATH = DOCS_GENERATED / 'runtime_contract_summary.md'
INDEX_PATH = DOCS / 'ROS2_INTERFACE_INDEX.md'
CONTRACT_INDEX_PATH = DOCS / 'CONTRACT_INDEX.md'
TOPIC_NAMES = BACKEND_SRC / 'arm_common' / 'arm_common' / 'topic_names.py'
SERVICE_NAMES = BACKEND_SRC / 'arm_common' / 'arm_common' / 'service_names.py'
ACTION_NAMES = BACKEND_SRC / 'arm_common' / 'arm_common' / 'action_names.py'
LAUNCH_FACTORY = BACKEND_SRC / 'arm_bringup' / 'arm_bringup' / 'launch_factory.py'
RUNTIME_PROFILES = BACKEND_SRC / 'arm_bringup' / 'config' / 'runtime_profiles.yaml'
TASK_CAPABILITY_MANIFEST = BACKEND_SRC / 'arm_bringup' / 'config' / 'task_capability_manifest.yaml'
RUNTIME_AUTHORITY = BACKEND_SRC / 'arm_bringup' / 'config' / 'runtime_authority.yaml'
PLACEMENT_PROFILES = BACKEND_SRC / 'arm_bringup' / 'config' / 'placement_profiles.yaml'
RUNTIME_PROMOTION_RECEIPTS = BACKEND_SRC / 'arm_bringup' / 'config' / 'runtime_promotion_receipts.yaml'
SAFETY_LIMITS = BACKEND_SRC / 'arm_bringup' / 'config' / 'safety_limits.yaml'
CONTRACT_DEFS = ROOT / 'backend' / 'embodied_arm_ws' / 'src' / 'arm_readiness_manager' / 'arm_readiness_manager' / 'contract_defs.py'
GATEWAY_RUNTIME_CONTRACT = ROOT / 'gateway' / 'generated' / 'runtime_contract.py'
FRONTEND_RUNTIME_CONTRACT = ROOT / 'frontend' / 'src' / 'generated' / 'runtimeContract.ts'

PUBLIC_TOPIC_KEYS = {
    'CAMERA_IMAGE_RAW',
    'CAMERA_INFO',
    'SYSTEM_STATE',
    'TASK_STATUS_TYPED',
    'HARDWARE_STATE',
    'FAULT_REPORT',
    'READINESS_STATE_TYPED',
    'BRINGUP_STATUS',
    'BRINGUP_STATUS_TYPED',
    'LOG_EVENT',
    'DIAGNOSTICS_SUMMARY_TYPED',
    'CALIBRATION_PROFILE_TYPED',
    'CAMERA_FRAME_SUMMARY',
    'CAMERA_HEALTH_SUMMARY',
    'VISION_TARGET',
    'VISION_TARGETS_TYPED',
    'VISION_SUMMARY',
}
COMPAT_TOPIC_KEYS = {
    'CAMERA_IMAGE_COMPAT',
    'TASK_STATUS',
    'READINESS_STATE',
    'CALIBRATION_PROFILE',
    'VISION_TARGETS',
    'DIAGNOSTICS_HEALTH',
}
INTERNAL_TOPIC_KEYS = {
    'INTERNAL_HARDWARE_CMD',
    'INTERNAL_ROS2_CONTROL_CMD',
    'INTERNAL_EXECUTION_STATUS',
    'INTERNAL_STOP_CMD',
}
PUBLIC_SERVICE_KEYS = (
    'START_TASK',
    'STOP_TASK',
    'STOP',
    'HOME',
    'RESET_FAULT',
    'CALIBRATION_MANAGER_RELOAD',
    'ACTIVATE_CALIBRATION',
    'SET_MODE',
)
PUBLIC_ACTION_KEYS = ('PICK_PLACE_TASK', 'MANUAL_SERVO', 'HOME_SEQUENCE', 'HOMING', 'RECOVER')
PACKAGE_OWNERSHIP = {
    'task orchestration': 'arm_task_orchestrator',
    'planning': 'arm_motion_planner',
    'execution': 'arm_motion_executor',
    'hardware io': 'arm_hardware_bridge',
    'readiness': 'arm_readiness_manager',
    'safety': 'arm_safety_supervisor',
    'perception input': 'arm_camera_driver',
    'perception processing': 'arm_perception',
    'lifecycle supervision': 'arm_lifecycle_manager',
}
TOPIC_SEMANTICS = {
    'CAMERA_IMAGE_RAW': 'standard sensor_msgs/Image ingress used by topic-backed camera runtime lanes',
    'CAMERA_INFO': 'camera intrinsic metadata paired with standard image ingress',
    'CAMERA_FRAME_SUMMARY': 'camera runtime freshness / source summary used by perception runtime',
    'CAMERA_HEALTH_SUMMARY': 'camera health projection for diagnostics / readiness',
    'VISION_TARGET': 'authoritative primary target contract used by readiness and command pipeline',
    'VISION_TARGETS': 'compatibility multi-target summary for UI aggregation and transitional consumers',
    'VISION_SUMMARY': 'perception runtime health / freshness summary',
    'BRINGUP_STATUS': 'JSON compatibility bringup / lifecycle summary',
    'BRINGUP_STATUS_TYPED': 'typed shadow bringup / lifecycle summary',
    'CAMERA_IMAGE_COMPAT': 'legacy JSON frame ingress kept only for migration compatibility',
    'INTERNAL_ROS2_CONTROL_CMD': 'internal ros2_control command metadata emitted by motion executor',
    'INTERNAL_EXECUTION_STATUS': 'internal execution-status stream used for task/executor correlation',
}


@dataclass(frozen=True)
class ConstantBlock:
    name: str
    values: dict[str, str]


class _LiteralExtractor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.assignments: dict[str, Any] = {}

    def visit_Assign(self, node: ast.Assign) -> None:
        try:
            value = self._resolve(node.value)
        except ValueError:
            self.generic_visit(node)
            return
        for target in node.targets:
            if isinstance(target, ast.Name):
                self.assignments[target.id] = value
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        if isinstance(node.target, ast.Name) and node.value is not None:
            try:
                self.assignments[node.target.id] = self._resolve(node.value)
            except ValueError:
                pass
        self.generic_visit(node)

    def _resolve(self, node: ast.AST) -> Any:
        if isinstance(node, ast.Constant):
            return node.value
        if isinstance(node, ast.Tuple):
            return tuple(self._resolve(item) for item in node.elts)
        if isinstance(node, ast.List):
            return [self._resolve(item) for item in node.elts]
        if isinstance(node, ast.Dict):
            return {self._resolve(key): self._resolve(value) for key, value in zip(node.keys, node.values)}
        if isinstance(node, ast.Name):
            if node.id not in self.assignments:
                raise ValueError(f'unresolved name: {node.id}')
            return self.assignments[node.id]
        if isinstance(node, ast.Subscript):
            value = self._resolve(node.value)
            key_node = node.slice.value if isinstance(node.slice, ast.Index) else node.slice
            key = self._resolve(key_node)
            return value[key]
        raise ValueError(f'unsupported literal node: {ast.dump(node)}')


def _extract_class_constants(path: Path, class_name: str) -> ConstantBlock:
    tree = ast.parse(path.read_text(encoding='utf-8'))
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            values: dict[str, str] = {}
            for item in node.body:
                if isinstance(item, ast.Assign) and len(item.targets) == 1 and isinstance(item.targets[0], ast.Name):
                    name = item.targets[0].id
                    value = item.value
                    if isinstance(value, ast.Constant) and isinstance(value.value, str):
                        values[name] = value.value
                    elif isinstance(value, ast.Name) and value.id in values:
                        values[name] = values[value.id]
            return ConstantBlock(name=class_name, values=values)
    raise RuntimeError(f'class {class_name} not found in {path}')


def _extract_module_literals(path: Path, *names: str) -> dict[str, Any]:
    tree = ast.parse(path.read_text(encoding='utf-8'))
    extractor = _LiteralExtractor()
    extractor.visit(tree)
    return {name: extractor.assignments[name] for name in names}


def _extract_contract_constants() -> dict[str, Any]:
    return _extract_module_literals(
        CONTRACT_DEFS,
        'PUBLIC_READINESS_FIELDS',
        'RUNTIME_HEALTH_REQUIRED',
        'READINESS_REQUIRED_BY_MODE',
        'PUBLIC_COMMAND_NAMES',
        'COMMAND_REQUIRED_BY_NAME',
        'COMMAND_ALLOWED_MODES',
        'HARDWARE_AUTHORITY_FIELDS',
        'SYSTEM_SEMANTIC_FIELDS',
        'COMPATIBILITY_ALIASES',
    )


def _extract_runtime_lane_capabilities() -> dict[str, dict[str, Any]]:
    authority = load_runtime_authority(RUNTIME_AUTHORITY)
    payload = derived_runtime_lanes(authority)
    capabilities: dict[str, dict[str, Any]] = {}
    for lane_name, lane_payload in sorted(payload.items()):
        capabilities[str(lane_name)] = {
            'frameIngressMode': str(lane_payload.get('frame_ingress_mode', 'reserved_endpoint')),
            'forwardHardwareCommands': bool(lane_payload.get('forward_hardware_commands', False)),
            'hardwareExecutionMode': str(lane_payload.get('hardware_execution_mode', 'protocol_bridge')),
            'esp32StreamSemantic': str(lane_payload.get('esp32_stream_semantic', 'reserved')),
            'esp32FrameIngressLive': bool(lane_payload.get('esp32_frame_ingress_live', False)),
            'planningCapability': str(lane_payload.get('planning_capability', 'contract_only')),
            'planningAuthoritative': bool(lane_payload.get('planning_authoritative', False)),
            'planningBackendDeclared': bool(lane_payload.get('planning_backend_declared', True)),
            'publicRuntimeTier': str(lane_payload.get('public_runtime_tier', '') or ''),
        }
    return capabilities


def _derive_runtime_tier(lane_payload: dict[str, Any]) -> str:
    public_runtime_tier = str(lane_payload.get('publicRuntimeTier', '') or '').strip()
    if public_runtime_tier in {'preview', 'validated_sim', 'validated_live'}:
        return public_runtime_tier
    planning_capability = str(lane_payload.get('planningCapability', 'contract_only') or 'contract_only')
    execution_mode = str(lane_payload.get('hardwareExecutionMode', 'protocol_bridge') or 'protocol_bridge')
    planning_authoritative = bool(lane_payload.get('planningAuthoritative', False))
    if planning_authoritative and execution_mode == 'ros2_control_live':
        return 'validated_live'
    if planning_authoritative and planning_capability == 'validated_sim':
        return 'validated_sim'
    return 'preview'


def _build_product_line_capabilities(lane_capabilities: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    authority = load_runtime_authority(RUNTIME_AUTHORITY)
    configured = derived_product_lines(authority)
    result: dict[str, dict[str, Any]] = {}
    for tier_name in ('preview', 'validated_sim', 'validated_live'):
        tier_payload = configured.get(tier_name, {}) if isinstance(configured, dict) else {}
        lanes = [lane_name for lane_name, lane_payload in sorted(lane_capabilities.items()) if lane_payload.get('runtimeTier') == tier_name]
        result[tier_name] = {
            'label': str(tier_payload.get('label', tier_name)),
            'description': str(tier_payload.get('description', '')),
            'taskWorkbenchVisible': bool(tier_payload.get('task_workbench_visible', tier_name != 'preview')),
            'taskExecutionInteractive': bool(tier_payload.get('task_execution_interactive', tier_name != 'preview')),
            'runtimeBadge': str(tier_payload.get('runtime_badge', tier_name.upper())),
            'promotionControlled': bool(tier_payload.get('promotion_controlled', False)),
            'promotionEffective': bool(tier_payload.get('promotion_effective', False)),
            'promotionMissing': [str(value) for value in tier_payload.get('promotion_missing', [])],
            'lanes': lanes,
        }
    return result


def _load_task_capabilities() -> dict[str, Any]:
    authority = load_runtime_authority(RUNTIME_AUTHORITY)
    payload = derived_task_manifest(authority)
    product_lines = payload.get('product_lines', {}) if isinstance(payload.get('product_lines'), dict) else {}
    templates: list[dict[str, Any]] = []
    for item in payload.get('templates', []):
        if not isinstance(item, dict):
            continue
        templates.append({
            'id': str(item.get('id', '')),
            'name': str(item.get('name', '')),
            'taskType': str(item.get('frontend_task_type', 'pick_place')),
            'backendTaskType': str(item.get('backend_task_type', 'PICK_AND_PLACE')),
            'description': str(item.get('description', '')),
            'defaultTargetCategory': str(item.get('default_target_category', '') or '') or None,
            'allowedTargetCategories': [str(value) for value in item.get('allowed_target_categories', []) if str(value).strip()],
            'resolvedPlaceProfiles': {str(key): str(value) for key, value in dict(item.get('resolved_place_profiles', {}) or {}).items()},
            'riskLevel': str(item.get('risk_level', 'medium')),
            'requiredRuntimeTier': str(item.get('required_runtime_tier', 'validated_sim')),
            'taskProfilePath': str(item.get('task_profile_path', '') or ''),
            'operatorHint': str(item.get('operator_hint', '')),
        })
    return {
        'schemaVersion': int(payload.get('schema_version', 1) or 1),
        'productLines': {
            key: {
                'label': str(value.get('label', key)),
                'description': str(value.get('description', '')),
                'taskWorkbenchVisible': bool(value.get('task_workbench_visible', key != 'preview')),
                'taskExecutionInteractive': bool(value.get('task_execution_interactive', key != 'preview')),
            }
            for key, value in product_lines.items()
            if isinstance(value, dict)
        },
        'templates': templates,
    }




def _load_runtime_promotion_receipts() -> dict[str, dict[str, Any]]:
    authority = load_runtime_authority(RUNTIME_AUTHORITY)
    payload = derived_promotion_receipts(authority)
    result: dict[str, dict[str, Any]] = {}
    for tier_name, item in payload.items():
        if not isinstance(item, dict):
            continue
        result[str(tier_name)] = {
            'promoted': bool(item.get('promoted', False)),
            'receiptId': str(item.get('receipt_id', '') or ''),
            'checkedBy': str(item.get('checked_by', '') or ''),
            'checkedAt': str(item.get('checked_at', '') or ''),
            'reason': str(item.get('reason', '') or ''),
            'requiredEvidence': [str(value) for value in item.get('required_evidence', []) if str(value).strip()],
            'evidence': [str(value) for value in item.get('evidence', []) if str(value).strip()],
            'effective': bool(item.get('effective', False)),
            'missingEvidence': [str(value) for value in item.get('missing_evidence', []) if str(value).strip()],
        }
    return result

def _camel_name(constant_name: str) -> str:
    parts = constant_name.lower().split('_')
    return parts[0] + ''.join(part.title() for part in parts[1:])




def _load_manual_command_limits() -> dict[str, float]:
    payload = yaml.safe_load(SAFETY_LIMITS.read_text(encoding='utf-8')) or {}
    if not isinstance(payload, dict):
        raise RuntimeError(f'invalid safety limits payload in {SAFETY_LIMITS}')
    manual = payload.get('manual_command_limits', {}) if isinstance(payload.get('manual_command_limits'), dict) else {}
    return {
        'maxServoCartesianDeltaMeters': float(manual.get('max_servo_cartesian_delta', 0.1)),
        'maxJogJointStepDeg': float(manual.get('max_jog_joint_step_deg', 10.0)),
    }

def build_contract_manifest() -> dict[str, Any]:
    topics = _extract_class_constants(TOPIC_NAMES, 'TopicNames').values
    services = _extract_class_constants(SERVICE_NAMES, 'ServiceNames').values
    actions = _extract_class_constants(ACTION_NAMES, 'ActionNames').values
    launch_literals = _extract_module_literals(LAUNCH_FACTORY, 'RUNTIME_CORE_PACKAGES', 'RUNTIME_SUPERVISION_PACKAGES', 'RUNTIME_LANE_ALIASES')
    gateway_constants = _extract_contract_constants()

    public_topics = {name: topics[name] for name in sorted(PUBLIC_TOPIC_KEYS)}
    compat_topics = {name: topics[name] for name in sorted(COMPAT_TOPIC_KEYS)}
    internal_topics = {name: topics[name] for name in sorted(INTERNAL_TOPIC_KEYS)}
    service_manifest = {_camel_name(name): services[name] for name in PUBLIC_SERVICE_KEYS}
    action_manifest = {_camel_name(name): actions[name] for name in PUBLIC_ACTION_KEYS}
    topic_manifest = {_camel_name(name): value for name, value in public_topics.items()}
    topic_manifest.update({_camel_name(name): value for name, value in compat_topics.items()})
    topic_manifest.update({_camel_name(name): value for name, value in internal_topics.items()})

    lane_capabilities = _extract_runtime_lane_capabilities()
    for lane_payload in lane_capabilities.values():
        lane_payload['runtimeTier'] = _derive_runtime_tier(lane_payload)
    task_capabilities = _load_task_capabilities()
    return {
        'schemaVersion': '1.5',
        'generatedFrom': 'scripts/generate_contract_artifacts.py',
        'readiness': {
            'publicFields': list(gateway_constants['PUBLIC_READINESS_FIELDS']),
            'runtimeHealthRequired': list(gateway_constants['RUNTIME_HEALTH_REQUIRED']),
            'requiredByMode': {name: list(values) for name, values in gateway_constants['READINESS_REQUIRED_BY_MODE'].items()},
            'commandNames': list(gateway_constants['PUBLIC_COMMAND_NAMES']),
            'commandRequiredByName': {name: list(values) for name, values in gateway_constants['COMMAND_REQUIRED_BY_NAME'].items()},
            'commandAllowedModes': {name: list(values) for name, values in gateway_constants['COMMAND_ALLOWED_MODES'].items()},
        },
        'hardware': {
            'authorityFields': list(gateway_constants['HARDWARE_AUTHORITY_FIELDS']),
            'manualCommandLimits': _load_manual_command_limits(),
        },
        'system': {
            'semanticFields': list(gateway_constants['SYSTEM_SEMANTIC_FIELDS']),
            'compatibilityAliases': dict(gateway_constants['COMPATIBILITY_ALIASES']),
        },
        'ros2': {
            'topics': topic_manifest,
            'services': service_manifest,
            'actions': action_manifest,
        },
        'runtime': {
            'corePackages': sorted(launch_literals['RUNTIME_CORE_PACKAGES']),
            'supervisionPackages': sorted(launch_literals['RUNTIME_SUPERVISION_PACKAGES']),
            'laneAliases': {key: launch_literals['RUNTIME_LANE_ALIASES'][key] for key in sorted(launch_literals['RUNTIME_LANE_ALIASES'])},
            'laneCapabilities': lane_capabilities,
            'promotionReceipts': _load_runtime_promotion_receipts(),
            'productLineCapabilities': _build_product_line_capabilities(lane_capabilities),
            'packageOwnership': {key: PACKAGE_OWNERSHIP[key] for key in sorted(PACKAGE_OWNERSHIP)},
        },
        'tasks': task_capabilities,
    }


def build_contract_markdown(manifest: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append('# Runtime Contract Summary (Generated)')
    lines.append('')
    lines.append('This file is generated by `scripts/generate_contract_artifacts.py` from backend authoritative contracts. Do not edit it manually.')
    lines.append('')
    lines.append(f"- Schema version: `{manifest['schemaVersion']}`")
    lines.append('')
    lines.append('## Readiness fields')
    for field in manifest['readiness']['publicFields']:
        lines.append(f'- `{field}`')
    lines.append('')
    lines.append('## Runtime-health required checks')
    for check in manifest['readiness']['runtimeHealthRequired']:
        lines.append(f'- `{check}`')
    lines.append('')
    lines.append('## Required checks by mode')
    for mode, checks in manifest['readiness']['requiredByMode'].items():
        lines.append(f"- `{mode}`: {', '.join(f'`{check}`' for check in checks)}")
    lines.append('')
    lines.append('## Public command-policy names')
    for name in manifest['readiness']['commandNames']:
        lines.append(f'- `{name}`')
    lines.append('')
    lines.append('## Command requirements by name')
    for name, checks in manifest['readiness']['commandRequiredByName'].items():
        rendered = ', '.join(f'`{check}`' for check in checks) or 'none'
        lines.append(f'- `{name}`: {rendered}')
    lines.append('')
    lines.append('## Command allowed modes')
    for name, modes in manifest['readiness']['commandAllowedModes'].items():
        rendered = ', '.join(f'`{mode}`' for mode in modes) or 'none'
        lines.append(f'- `{name}`: {rendered}')
    lines.append('')
    lines.append('## Hardware authority fields')
    for field in manifest['hardware']['authorityFields']:
        lines.append(f'- `{field}`')
    lines.append('')
    lines.append('## Manual command limits')
    for name, value in manifest['hardware']['manualCommandLimits'].items():
        lines.append(f'- `{name}`: `{value}`')
    lines.append('')
    lines.append('## Semantic fields and compatibility aliases')
    for field in manifest['system']['semanticFields']:
        lines.append(f'- semantic: `{field}`')
    for legacy, modern in manifest['system']['compatibilityAliases'].items():
        lines.append(f'- alias: `{legacy}` -> `{modern}`')
    lines.append('')
    lines.append('## ROS 2 topics')
    for name, value in manifest['ros2']['topics'].items():
        lines.append(f'- `{name}`: `{value}`')
    lines.append('')
    lines.append('## ROS 2 services')
    for name, value in manifest['ros2']['services'].items():
        lines.append(f'- `{name}`: `{value}`')
    lines.append('')
    lines.append('## ROS 2 actions')
    for name, value in manifest['ros2']['actions'].items():
        lines.append(f'- `{name}`: `{value}`')
    lines.append('')
    lines.append('## Runtime lanes')
    for alias, target in sorted(manifest['runtime']['laneAliases'].items()):
        lines.append(f'- alias: `{alias}` -> `{target}`')
    lines.append('')
    lines.append('## Runtime lane capabilities')
    for lane_name, lane_payload in sorted(manifest['runtime']['laneCapabilities'].items()):
        lines.append(
            '- '
            f'`{lane_name}`: '
            f"frameIngressMode=`{lane_payload['frameIngressMode']}`, "
            f"forwardHardwareCommands=`{lane_payload['forwardHardwareCommands']}`, "
            f"hardwareExecutionMode=`{lane_payload['hardwareExecutionMode']}`, "
            f"planningCapability=`{lane_payload['planningCapability']}`, "
            f"planningAuthoritative=`{lane_payload['planningAuthoritative']}`"
        )
    lines.append('')
    lines.append('## Runtime promotion receipts')
    for tier_name, receipt_payload in sorted(manifest['runtime']['promotionReceipts'].items()):
        lines.append(
            '- '
            f'`{tier_name}`: '
            f"promoted=`{receipt_payload['promoted']}`, "
            f"receiptId=`{receipt_payload['receiptId']}`, "
            f"checkedBy=`{receipt_payload['checkedBy']}`, "
            f"checkedAt=`{receipt_payload['checkedAt']}`"
        )
    lines.append('')
    lines.append('## Runtime product lines')
    for tier_name, tier_payload in sorted(manifest['runtime']['productLineCapabilities'].items()):
        lines.append(
            '- '
            f'`{tier_name}`: '
            f"label=`{tier_payload['label']}`, "
            f"taskWorkbenchVisible=`{tier_payload['taskWorkbenchVisible']}`, "
            f"taskExecutionInteractive=`{tier_payload['taskExecutionInteractive']}`, "
            f"lanes=`{', '.join(tier_payload['lanes'])}`"
        )
    lines.append('')
    lines.append('## Task capability templates')
    for template in manifest['tasks']['templates']:
        selectors = ', '.join(f'`{item}`' for item in template['allowedTargetCategories']) or 'none'
        place_profiles = ', '.join(f'`{key}->{value}`' for key, value in template['resolvedPlaceProfiles'].items()) or 'none'
        lines.append(
            '- '
            f"`{template['id']}`: taskType=`{template['taskType']}`, "
            f"backendTaskType=`{template['backendTaskType']}`, "
            f"requiredRuntimeTier=`{template['requiredRuntimeTier']}`, "
            f"targetSelectors={selectors}, "
            f"placeProfiles={place_profiles}"
        )
    lines.append('')
    lines.append('## Runtime package ownership')
    for role, package in sorted(manifest['runtime']['packageOwnership'].items()):
        lines.append(f'- `{role}`: `{package}`')
    lines.append('')
    return '\n'.join(lines)


def build_interface_index(manifest: dict[str, Any]) -> str:
    topics = _extract_class_constants(TOPIC_NAMES, 'TopicNames').values
    services = _extract_class_constants(SERVICE_NAMES, 'ServiceNames').values
    actions = _extract_class_constants(ACTION_NAMES, 'ActionNames').values
    lines = [
        '# ROS 2 Interface Index',
        '',
        '> Generated from `arm_common/topic_names.py`, `service_names.py`, `action_names.py`, and `arm_bringup/launch_factory.py`.',
        '',
        '## Authoritative topics',
    ]
    for key in sorted(PUBLIC_TOPIC_KEYS):
        lines.append(f'- `{topics[key]}`')
    lines.extend(['', '## Compatibility / aggregation topics'])
    for key in sorted(COMPAT_TOPIC_KEYS):
        lines.append(f'- `{topics[key]}`')
    lines.extend(['', '## Internal control topics'])
    for key in sorted(INTERNAL_TOPIC_KEYS):
        lines.append(f'- `{topics[key]}`')
    lines.extend(['', '## Topic semantics', ''])
    for key, description in sorted(TOPIC_SEMANTICS.items()):
        lines.append(f'- `{topics[key]}`: {description}')
    lines.extend(['', '## Services'])
    for key in sorted(PUBLIC_SERVICE_KEYS):
        lines.append(f'- `{services[key]}`')
    lines.extend(['', '## Actions'])
    for key in sorted(PUBLIC_ACTION_KEYS):
        lines.append(f'- `{actions[key]}`')
    lines.extend(['', '## Package ownership'])
    for role, package in sorted(PACKAGE_OWNERSHIP.items()):
        lines.append(f'- {role}: `{package}`')
    lines.extend(['', '## Runtime lanes'])
    for alias, target in sorted(manifest['runtime']['laneAliases'].items()):
        lines.append(f'- `{alias}` -> `{target}`')
    lines.append('')
    return '\n'.join(lines)







def build_gateway_runtime_contract(manifest: dict[str, Any]) -> str:
    readiness = manifest['readiness']
    hardware = manifest['hardware']
    system = manifest['system']
    readiness_required = {key: tuple(value) for key, value in readiness['requiredByMode'].items()}
    all_checks = tuple(dict.fromkeys([*readiness['runtimeHealthRequired'], *[item for values in readiness['requiredByMode'].values() for item in values]]))
    contract_constants = _extract_contract_constants()
    command_required = {key: tuple(value) for key, value in contract_constants['COMMAND_REQUIRED_BY_NAME'].items()}
    command_modes = {key: tuple(value) for key, value in contract_constants['COMMAND_ALLOWED_MODES'].items()}
    lines = [
        'from __future__ import annotations',
        '',
        '"""Generated gateway runtime-contract mirror. Do not edit manually."""',
        '',
        'from typing import Any, Iterable',
        '',
        f"PUBLIC_READINESS_FIELDS = {tuple(readiness['publicFields'])!r}",
        f"RUNTIME_HEALTH_REQUIRED = {tuple(readiness['runtimeHealthRequired'])!r}",
        f"READINESS_REQUIRED_BY_MODE = {readiness_required!r}",
        f"ALL_READINESS_CHECKS = {all_checks!r}",
        f"PUBLIC_COMMAND_NAMES = {tuple(readiness['commandNames'])!r}",
        f"COMMAND_REQUIRED_BY_NAME = {command_required!r}",
        f"COMMAND_ALLOWED_MODES = {command_modes!r}",
        f"HARDWARE_AUTHORITY_FIELDS = {tuple(hardware['authorityFields'])!r}",
        f"SYSTEM_SEMANTIC_FIELDS = {tuple(system['semanticFields'])!r}",
        f"COMPATIBILITY_ALIASES = {dict(system['compatibilityAliases'])!r}",
        f"PRODUCT_LINE_CAPABILITIES = {manifest['runtime']['productLineCapabilities']!r}",
        f"TASK_CAPABILITY_TEMPLATES = {manifest['tasks']['templates']!r}",
        '',
        'def required_checks_for_mode(mode: str) -> tuple[str, ...]:',
        '    normalized = str(mode or "").strip().lower()',
        "    return READINESS_REQUIRED_BY_MODE.get(normalized, READINESS_REQUIRED_BY_MODE['task'])",
        '',
        'def _command_policy(allowed: bool, reason: str) -> dict[str, Any]:',
        "    return {'allowed': bool(allowed), 'reason': str(reason)}",
        '',
        'def _effective_check_ok(checks: dict[str, Any], name: str) -> bool:',
        "    payload = checks.get(name, {})",
        "    return bool(payload.get('effectiveOk', payload.get('ok', False)))",
        '',
        'def _missing_required_checks(checks: dict[str, dict[str, Any]], names: Iterable[str]) -> list[str]:',
        '    return [name for name in names if not _effective_check_ok(checks, name)]',
        '',
        'def _missing_reason(checks: dict[str, dict[str, Any]], missing: list[str], default_reason: str) -> str:',
        '    if not missing:',
        '        return default_reason',
        '    detailed: list[str] = []',
        '    for name in missing:',
        "        payload = checks.get(name, {})",
        "        detail = str(payload.get('detail', '') or '').strip()",
        "        detailed.append(f'{name}({detail})' if detail else name)",
        "    return 'missing readiness: ' + ', '.join(detailed)",
        '',
        'def build_command_policies(mode: str, checks: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:',
        "    normalized_mode = str(mode or '').strip().lower() or 'boot'",
        "    start_missing = _missing_required_checks(checks, COMMAND_REQUIRED_BY_NAME['startTask'])",
        "    manual_missing = _missing_required_checks(checks, COMMAND_REQUIRED_BY_NAME['jog'])",
        "    home_missing = _missing_required_checks(checks, COMMAND_REQUIRED_BY_NAME['home'])",
        "    reset_missing = _missing_required_checks(checks, COMMAND_REQUIRED_BY_NAME['resetFault'])",
        "    recover_missing = _missing_required_checks(checks, COMMAND_REQUIRED_BY_NAME['recover'])",
        '',
        "    start_allowed = normalized_mode in COMMAND_ALLOWED_MODES['startTask'] and not start_missing",
        "    manual_ready = normalized_mode in COMMAND_ALLOWED_MODES['jog'] and not manual_missing",
        "    stop_allowed = normalized_mode in COMMAND_ALLOWED_MODES['stopTask']",
        "    hardware_fault = bool(checks.get('hardware_bridge', {}).get('detail') in {'fault', 'hardware_blocked', 'hardware_fault'})",
        "    home_allowed = normalized_mode in COMMAND_ALLOWED_MODES['home'] and not home_missing and not hardware_fault",
        "    reset_allowed = normalized_mode in COMMAND_ALLOWED_MODES['resetFault'] and not reset_missing",
        "    recover_allowed = normalized_mode in COMMAND_ALLOWED_MODES['recover'] and not recover_missing",
        '',
        '    if start_allowed:',
        "        start_reason = 'ready'",
        '    elif start_missing:',
        "        start_reason = _missing_reason(checks, start_missing, 'task execution requires authoritative runtime lane')",
        '    else:',
        "        start_reason = f'mode {normalized_mode} does not allow task start'",
        '',
        "    manual_reason = 'ready' if manual_ready else (_missing_reason(checks, manual_missing, 'manual operations require manual or maintenance mode') if manual_missing else 'manual operations require manual or maintenance mode')",
        '',
        '    if home_allowed:',
        "        home_reason = 'ready'",
        '    elif hardware_fault:',
        "        home_reason = 'home blocked by hardware fault'",
        "    elif normalized_mode not in COMMAND_ALLOWED_MODES['home']:",
        "        home_reason = 'home blocked by current runtime mode'",
        '    else:',
        "        home_reason = _missing_reason(checks, home_missing, 'missing readiness: hardware_bridge')",
        '',
        '    if reset_allowed:',
        "        reset_reason = 'ready'",
        '    elif reset_missing:',
        "        reset_reason = _missing_reason(checks, reset_missing, 'reset fault requires authoritative hardware bridge')",
        '    else:',
        "        reset_reason = 'reset fault only valid in fault or safe-stop mode'",
        '',
        '    if recover_allowed:',
        "        recover_reason = 'ready'",
        '    elif recover_missing:',
        "        recover_reason = _missing_reason(checks, recover_missing, 'recover requires authoritative runtime control path')",
        '    else:',
        "        recover_reason = 'recover only valid in idle / maintenance / fault / safe-stop mode'",
        '',
        '    return {',
        "        'startTask': _command_policy(start_allowed, start_reason),",
        "        'stopTask': _command_policy(stop_allowed, 'ready' if stop_allowed else 'no active runtime command path'),",
        "        'jog': _command_policy(manual_ready, manual_reason),",
        "        'servoCartesian': _command_policy(manual_ready, manual_reason),",
        "        'gripper': _command_policy(manual_ready, manual_reason),",
        "        'home': _command_policy(home_allowed, home_reason),",
        "        'resetFault': _command_policy(reset_allowed, reset_reason),",
        "        'recover': _command_policy(recover_allowed, recover_reason),",
        '    }',
        '',
        'def build_readiness_layers(mode: str, checks: dict[str, dict[str, Any]]) -> tuple[bool, bool]:',
        "    runtime_healthy = all(bool(checks.get(name, {}).get('effectiveOk', checks.get(name, {}).get('ok', False))) for name in RUNTIME_HEALTH_REQUIRED)",
        '    required = required_checks_for_mode(mode)',
        "    mode_ready = bool(required) and all(bool(checks.get(name, {}).get('effectiveOk', checks.get(name, {}).get('ok', False))) for name in required)",
        '    return runtime_healthy, mode_ready',
        '',
    ]
    return '\n'.join(lines)


def build_frontend_runtime_contract(manifest: dict[str, Any]) -> str:
    readiness = manifest['readiness']
    hardware = manifest['hardware']
    system = manifest['system']
    return '\n'.join([
        '// Generated by scripts/generate_contract_artifacts.py from backend authoritative contracts. Do not edit manually.',
        '',
        f"export const PUBLIC_READINESS_FIELDS = {json.dumps(readiness['publicFields'], ensure_ascii=False)} as const;" ,
        f"export const RUNTIME_HEALTH_REQUIRED = {json.dumps(readiness['runtimeHealthRequired'], ensure_ascii=False)} as const;" ,
        f"export const READINESS_REQUIRED_BY_MODE = {json.dumps(readiness['requiredByMode'], ensure_ascii=False, indent=2)} as const;" ,
        f"export const PUBLIC_COMMAND_NAMES = {json.dumps(readiness['commandNames'], ensure_ascii=False)} as const;" ,
        f"export const HARDWARE_AUTHORITY_FIELDS = {json.dumps(hardware['authorityFields'], ensure_ascii=False)} as const;" ,
        f"export const MANUAL_COMMAND_LIMITS = {json.dumps(hardware['manualCommandLimits'], ensure_ascii=False, indent=2)} as const;" ,
        f"export const SYSTEM_SEMANTIC_FIELDS = {json.dumps(system['semanticFields'], ensure_ascii=False)} as const;" ,
        f"export const COMPATIBILITY_ALIASES = {json.dumps(system['compatibilityAliases'], ensure_ascii=False, indent=2)} as const;" ,
        f"export const PRODUCT_LINE_CAPABILITIES = {json.dumps(manifest['runtime']['productLineCapabilities'], ensure_ascii=False, indent=2)} as const;" ,
        f"export const TASK_CAPABILITY_TEMPLATES = {json.dumps(manifest['tasks']['templates'], ensure_ascii=False, indent=2)} as const;" ,
        '',
        'export type PublicCommandName = typeof PUBLIC_COMMAND_NAMES[number];',
        'export type RuntimeHealthCheck = typeof RUNTIME_HEALTH_REQUIRED[number];',
        'export type ReadinessMode = keyof typeof READINESS_REQUIRED_BY_MODE;',
        '',
    ])


def build_contract_index() -> str:
    return '\n'.join([
        '# Contract Index',
        '',
        'Authoritative contract artifacts are generated from backend readiness contracts plus ROS interface definitions. Do not hand-edit generated interface lists.',
        '',
        '## Generated artifacts',
        '- `generated/runtime_contract_manifest.json`',
        '- `generated/runtime_contract_summary.md`',
        '- `ROS2_INTERFACE_INDEX.md`',
        '',
        '## Source of truth',
        '- `backend/embodied_arm_ws/src/arm_common/arm_common/topic_names.py`',
        '- `backend/embodied_arm_ws/src/arm_common/arm_common/service_names.py`',
        '- `backend/embodied_arm_ws/src/arm_common/arm_common/action_names.py`',
        '- `backend/embodied_arm_ws/src/arm_bringup/arm_bringup/launch_factory.py`',
        '- `backend/embodied_arm_ws/src/arm_readiness_manager/arm_readiness_manager/contract_defs.py`',
        '- `backend/embodied_arm_ws/src/arm_bringup/config/task_capability_manifest.yaml`',
        '- `gateway/generated/runtime_contract.py`',
        '- `frontend/src/generated/runtimeContract.ts`',
        '',
    ])


def render_outputs() -> dict[Path, str]:
    manifest = build_contract_manifest()
    return {
        JSON_PATH: json.dumps(manifest, ensure_ascii=False, indent=2) + '\n',
        MD_PATH: build_contract_markdown(manifest) + '\n',
        INDEX_PATH: build_interface_index(manifest) + '\n',
        CONTRACT_INDEX_PATH: build_contract_index() + '\n',
        GATEWAY_RUNTIME_CONTRACT: build_gateway_runtime_contract(manifest),
        FRONTEND_RUNTIME_CONTRACT: build_frontend_runtime_contract(manifest),
    }


def write_outputs() -> None:
    outputs = render_outputs()
    DOCS_GENERATED.mkdir(parents=True, exist_ok=True)
    for path, content in outputs.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding='utf-8')


def check_outputs() -> int:
    outputs = render_outputs()
    stale: list[str] = []
    for path, content in outputs.items():
        if not path.exists() or path.read_text(encoding='utf-8') != content:
            stale.append(str(path.relative_to(ROOT)))
    if stale:
        print('stale contract artifacts detected:')
        for item in stale:
            print(f'- {item}')
        return 1
    print('contract artifacts are in sync')
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--check', action='store_true', help='fail if checked-in generated artifacts are stale')
    args = parser.parse_args()
    if args.check:
        return check_outputs()
    write_outputs()
    for path in render_outputs():
        print(f'generated: {path.relative_to(ROOT)}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
