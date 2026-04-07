from __future__ import annotations

import argparse
import ast
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

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
CONTRACT_DEFS = ROOT / 'backend' / 'embodied_arm_ws' / 'src' / 'arm_readiness_manager' / 'arm_readiness_manager' / 'contract_defs.py'
GATEWAY_RUNTIME_CONTRACT = ROOT / 'gateway' / 'generated' / 'runtime_contract.py'
FRONTEND_RUNTIME_CONTRACT = ROOT / 'frontend' / 'src' / 'generated' / 'runtimeContract.ts'

PUBLIC_TOPIC_KEYS = {
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
    'TASK_STATUS',
    'READINESS_STATE',
    'CALIBRATION_PROFILE',
    'VISION_TARGETS',
    'DIAGNOSTICS_HEALTH',
}
INTERNAL_TOPIC_KEYS = {
    'INTERNAL_HARDWARE_CMD',
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
    'CAMERA_FRAME_SUMMARY': 'camera runtime freshness / source summary used by perception runtime',
    'CAMERA_HEALTH_SUMMARY': 'camera health projection for diagnostics / readiness',
    'VISION_TARGET': 'authoritative primary target contract used by readiness and command pipeline',
    'VISION_TARGETS': 'compatibility multi-target summary for UI aggregation and transitional consumers',
    'VISION_SUMMARY': 'perception runtime health / freshness summary',
    'BRINGUP_STATUS': 'JSON compatibility bringup / lifecycle summary',
    'BRINGUP_STATUS_TYPED': 'typed shadow bringup / lifecycle summary',
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
        'HARDWARE_AUTHORITY_FIELDS',
        'SYSTEM_SEMANTIC_FIELDS',
        'COMPATIBILITY_ALIASES',
    )


def _camel_name(constant_name: str) -> str:
    parts = constant_name.lower().split('_')
    return parts[0] + ''.join(part.title() for part in parts[1:])


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

    return {
        'schemaVersion': '1.4',
        'generatedFrom': 'scripts/generate_contract_artifacts.py',
        'readiness': {
            'publicFields': list(gateway_constants['PUBLIC_READINESS_FIELDS']),
            'runtimeHealthRequired': list(gateway_constants['RUNTIME_HEALTH_REQUIRED']),
            'requiredByMode': {name: list(values) for name, values in gateway_constants['READINESS_REQUIRED_BY_MODE'].items()},
            'commandNames': list(gateway_constants['PUBLIC_COMMAND_NAMES']),
        },
        'hardware': {
            'authorityFields': list(gateway_constants['HARDWARE_AUTHORITY_FIELDS']),
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
            'packageOwnership': {key: PACKAGE_OWNERSHIP[key] for key in sorted(PACKAGE_OWNERSHIP)},
        },
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
    lines.append('## Hardware authority fields')
    for field in manifest['hardware']['authorityFields']:
        lines.append(f'- `{field}`')
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
    lines = [
        'from __future__ import annotations',
        '',
        '"""Generated gateway runtime-contract mirror. Do not edit manually."""',
        '',
        'from typing import Any',
        '',
        f"PUBLIC_READINESS_FIELDS = {tuple(readiness['publicFields'])!r}",
        f"RUNTIME_HEALTH_REQUIRED = {tuple(readiness['runtimeHealthRequired'])!r}",
        f"READINESS_REQUIRED_BY_MODE = {readiness_required!r}",
        f"ALL_READINESS_CHECKS = {all_checks!r}",
        f"PUBLIC_COMMAND_NAMES = {tuple(readiness['commandNames'])!r}",
        f"HARDWARE_AUTHORITY_FIELDS = {tuple(hardware['authorityFields'])!r}",
        f"SYSTEM_SEMANTIC_FIELDS = {tuple(system['semanticFields'])!r}",
        f"COMPATIBILITY_ALIASES = {dict(system['compatibilityAliases'])!r}",
        '',
        'def required_checks_for_mode(mode: str) -> tuple[str, ...]:',
        '    normalized = str(mode or "").strip().lower()',
        "    return READINESS_REQUIRED_BY_MODE.get(normalized, READINESS_REQUIRED_BY_MODE['task'])",
        '',
        'def _command_policy(allowed: bool, reason: str) -> dict[str, Any]:',
        "    return {'allowed': bool(allowed), 'reason': str(reason)}",
        '',
        'def build_command_policies(mode: str, checks: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:',
        "    task_required = [name for name in required_checks_for_mode('task') if name in checks]",
        "    missing_task = [name for name in task_required if not bool(checks.get(name, {}).get('effectiveOk', checks.get(name, {}).get('ok')))]",
        "    manual_required = [name for name in required_checks_for_mode('manual') if name in checks]",
        "    missing_manual = [name for name in manual_required if not bool(checks.get(name, {}).get('effectiveOk', checks.get(name, {}).get('ok')))]",
        '',
        '    def _missing_reason(missing: list[str], default_reason: str) -> str:',
        "        return 'missing readiness: ' + ', '.join(missing) if missing else default_reason",
        '',
        "    start_allowed = mode not in {'boot', 'safe_stop', 'fault'} and not missing_task",
        "    manual_mode_enabled = mode in {'manual', 'maintenance'}",
        '    manual_ready = manual_mode_enabled and not missing_manual',
        "    hardware_fault = bool(checks.get('hardware_bridge', {}).get('detail') in {'fault', 'hardware_blocked'})",
        '    return {',
        "        'startTask': _command_policy(start_allowed, 'ready' if start_allowed else _missing_reason(missing_task, f'mode {mode} does not allow task start')),",
        "        'stopTask': _command_policy(mode in {'task', 'manual', 'maintenance', 'safe_stop', 'fault'}, 'ready' if mode in {'task', 'manual', 'maintenance', 'safe_stop', 'fault'} else 'no active runtime command path'),",
        "        'jog': _command_policy(manual_ready, 'ready' if manual_ready else _missing_reason(missing_manual, 'manual operations require manual or maintenance mode')),",
        "        'servoCartesian': _command_policy(manual_ready, 'ready' if manual_ready else _missing_reason(missing_manual, 'manual operations require manual or maintenance mode')),",
        "        'gripper': _command_policy(manual_ready, 'ready' if manual_ready else _missing_reason(missing_manual, 'manual operations require manual or maintenance mode')),",
        "        'home': _command_policy(mode not in {'safe_stop'} and not hardware_fault, 'ready' if mode not in {'safe_stop'} and not hardware_fault else 'home blocked by safe-stop or hardware fault'),",
        "        'resetFault': _command_policy(mode in {'fault', 'safe_stop'}, 'ready' if mode in {'fault', 'safe_stop'} else 'reset fault only valid in fault or safe-stop mode'),",
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
        f"export const SYSTEM_SEMANTIC_FIELDS = {json.dumps(system['semanticFields'], ensure_ascii=False)} as const;" ,
        f"export const COMPATIBILITY_ALIASES = {json.dumps(system['compatibilityAliases'], ensure_ascii=False, indent=2)} as const;" ,
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
