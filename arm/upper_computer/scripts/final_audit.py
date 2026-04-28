from __future__ import annotations

import ast
import hashlib
import json
from importlib import util as importlib_util
try:
    import yaml
except ModuleNotFoundError:  # pragma: no cover - exercised in clean stdlib audit environments.
    import sys as _yaml_compat_sys
    from pathlib import Path as _YamlCompatPath
    _yaml_compat_root = _YamlCompatPath(__file__).resolve().parents[1]
    if str(_yaml_compat_root) not in _yaml_compat_sys.path:
        _yaml_compat_sys.path.insert(0, str(_yaml_compat_root))
    from scripts import yaml_compat as yaml
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT))
from scripts.check_active_profile_consistency import (
    DEPRECATED_PACKAGES as ACTIVE_LANE_COMPATIBILITY_PACKAGES,
    EXPERIMENTAL_PACKAGES as ACTIVE_LANE_EXPERIMENTAL_PACKAGES,
)
from scripts.package_release import EXCLUDE_PREFIXES as RELEASE_EXCLUDE_PREFIXES, should_skip as release_should_skip
from runtime_authority import load_runtime_authority, load_validated_live_evidence, evaluate_promotion_receipt, validate_runtime_authority_consistency, validated_live_artifact_issues
from scripts.check_public_interface_ownership import validate_public_interface_ownership
from scripts.generate_contract_artifacts import render_outputs as render_contract_outputs
from scripts.sync_doc_compatibility_mirrors import MANIFEST_PATH as DOC_COMPATIBILITY_MANIFEST_PATH, render_outputs as render_doc_compatibility_outputs
from scripts.write_frontend_validation_status import check_outputs as check_frontend_validation_outputs
from scripts.release_state_model import build_release_gate_report

SRC = ROOT / 'backend' / 'embodied_arm_ws' / 'src'
DEPRECATED = {'arm_msgs'} | set(ACTIVE_LANE_COMPATIBILITY_PACKAGES)
EXPERIMENTAL = set(ACTIVE_LANE_EXPERIMENTAL_PACKAGES)
ALLOW_ARM_MSGS = {
    SRC / 'arm_common' / 'arm_common' / 'interface_compat.py',
    ROOT / 'gateway' / 'ros_contract.py',
}
ALLOW_RAW_TOPIC_FILES = {
    SRC / 'arm_common' / 'arm_common' / 'topic_names.py',
    SRC / 'arm_common' / 'arm_common' / 'service_names.py',
    SRC / 'arm_common' / 'arm_common' / 'action_names.py',
    SRC / 'arm_motion_executor' / 'arm_motion_executor' / 'motion_executor_node.py',
    SRC / 'arm_motion_planner' / 'arm_motion_planner' / 'motion_planner_node.py',
    SRC / 'arm_scene_manager' / 'arm_scene_manager' / 'scene_manager_node.py',
    SRC / 'arm_grasp_planner' / 'arm_grasp_planner' / 'grasp_planner_node.py',
    SRC / 'arm_readiness_manager' / 'arm_readiness_manager' / 'readiness_manager_node.py',
    SRC / 'arm_readiness_manager' / 'arm_readiness_manager' / 'mode_coordinator_node.py',
    SRC / 'arm_task_orchestrator' / 'arm_task_orchestrator' / 'task_orchestrator_node.py',
    ROOT / 'gateway' / 'ros_contract.py',
}


VALIDATED_LIVE_EVIDENCE = ROOT / 'backend' / 'embodied_arm_ws' / 'src' / 'arm_bringup' / 'config' / 'validated_live_evidence.yaml'
RUNTIME_PROMOTION_RECEIPTS = ROOT / 'backend' / 'embodied_arm_ws' / 'src' / 'arm_bringup' / 'config' / 'runtime_promotion_receipts.yaml'
DELIVERY_REPORT = ROOT / 'DELIVERY_REPORT.md'


def _load_json_dict(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _sha256_file(path: Path) -> str:
    """Return the SHA-256 digest for a regular evidence file.

    Args:
        path: Existing file path to hash.

    Returns:
        Lowercase hexadecimal SHA-256 digest.

    Raises:
        FileNotFoundError: If the evidence file is absent.
        IsADirectoryError: If the evidence path is not a regular file.

    Boundary behavior:
        The digest is computed over raw bytes only. Self-referential evidence
        ledgers are not passed to this helper because they cannot contain their
        own final digest.
    """
    if not path.is_file():
        raise IsADirectoryError(str(path))
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _audit_release_evidence_file_provenance(payload: dict) -> list[str]:
    """Validate release_evidence.json per-file provenance records.

    Args:
        payload: Parsed `artifacts/release_gates/release_evidence.json` object.

    Returns:
        A list of audit issues. Empty means every recorded evidence file has
        correct existence, size and SHA-256 metadata, and exactly one canonical
        ledger self-reference is present.

    Boundary behavior:
        `artifacts/release_gates/release_evidence.json` must appear exactly once
        with `provenanceStatus=self_referential_output`, `exists=True`, and null
        digest/size fields because a file cannot embed a stable hash of itself.
        All other existing files must be `recorded` and hash-verifiable.
    """
    expected_self_path = 'artifacts/release_gates/release_evidence.json'
    raw_evidence = payload.get('evidence')
    issues: list[str] = []
    if not isinstance(raw_evidence, list):
        return ['release_evidence.json evidence must be a list']
    self_reference_count = 0
    for item in raw_evidence:
        if not isinstance(item, dict):
            issues.append('release_evidence.json evidence entries must be objects')
            continue
        rel = str(item.get('path', '') or '').strip()
        if not rel:
            issues.append('release_evidence.json evidence entry missing path')
            continue
        status = str(item.get('provenanceStatus', '') or '')
        if status == 'self_referential_output':
            if rel == expected_self_path:
                self_reference_count += 1
            else:
                issues.append(f'release_evidence.json invalid self-referential provenance path: {rel}')
            if item.get('exists') is not True:
                issues.append(f'release_evidence.json self-reference must record post-write exists=true: {rel}')
            if item.get('sha256') is not None or item.get('sizeBytes') is not None or item.get('size') is not None:
                issues.append(f'release_evidence.json self-reference must not record stale hash/size: {rel}')
            continue
        absolute = ROOT / rel
        exists = absolute.exists()
        if bool(item.get('exists', False)) != exists:
            issues.append(f'release_evidence.json exists drift for {rel}')
        if not exists:
            if status != 'missing':
                issues.append(f'release_evidence.json missing file must use provenanceStatus=missing: {rel}')
            continue
        if not absolute.is_file():
            if status != 'not_a_file':
                issues.append(f'release_evidence.json non-file must use provenanceStatus=not_a_file: {rel}')
            continue
        if status != 'recorded':
            issues.append(f'release_evidence.json evidence file must use provenanceStatus=recorded: {rel}')
        size = absolute.stat().st_size
        if item.get('sizeBytes') != size or item.get('size') != size:
            issues.append(f'release_evidence.json size drift for {rel}')
        if str(item.get('sha256', '') or '') != _sha256_file(absolute):
            issues.append(f'release_evidence.json sha256 drift for {rel}')
    if self_reference_count == 0:
        issues.append(f'release_evidence.json missing self-reference entry: {expected_self_path}')
    elif self_reference_count > 1:
        issues.append(f'release_evidence.json duplicate self-reference entry: {expected_self_path}')
    return issues


def _authoritative_release_gate_report() -> dict:
    gate_report = ROOT / 'artifacts' / 'release_gates' / 'target_runtime_gate.json'
    release_evidence = ROOT / 'artifacts' / 'release_gates' / 'release_evidence.json'
    env_report = ROOT / 'artifacts' / 'target_env_report.json'
    runtime_baseline_report = ROOT / 'artifacts' / 'release_gates' / 'runtime_baseline_report.json'
    gate_payload = _load_json_dict(gate_report)
    steps = gate_payload.get('steps', {}) if isinstance(gate_payload.get('steps'), dict) else {}
    normalized_steps = {str(name): str(value or 'not_executed') for name, value in dict(steps).items()}
    env_payload = _load_json_dict(env_report)
    if 'env' not in normalized_steps:
        normalized_steps['env'] = 'passed' if bool(env_payload.get('ok', False)) else ('blocked' if env_payload else 'not_executed')
    baseline_payload = _load_json_dict(runtime_baseline_report)
    if 'runtime_baseline' not in normalized_steps:
        normalized_steps['runtime_baseline'] = str(baseline_payload.get('status', 'not_executed') or 'not_executed')
    normalized_steps.setdefault('ros_build', 'not_executed')
    normalized_steps.setdefault('ros_smoke', 'not_executed')
    normalized_steps.setdefault('negative_path_subset', 'not_executed')
    normalized_steps.setdefault('hil', 'not_executed')
    normalized_steps.setdefault('release_checklist', 'not_executed')
    return build_release_gate_report(env_payload, normalized_steps, root=ROOT, evidence_path=str(release_evidence))


def _active_python_files() -> list[Path]:
    files = []
    for path in SRC.rglob('*.py'):
        if any(part in (DEPRECATED | EXPERIMENTAL) for part in path.parts):
            continue
        files.append(path)
    for path in ROOT.joinpath('gateway').rglob('*.py'):
        if 'tests' in path.parts or '__pycache__' in path.parts:
            continue
        files.append(path)
    return files


def audit_arm_msgs_imports() -> list[str]:
    issues = []
    for path in _active_python_files():
        if path in ALLOW_ARM_MSGS:
            continue
        text = path.read_text(encoding='utf-8')
        if 'arm_msgs' in text:
            issues.append(f'active file still references arm_msgs: {path.relative_to(ROOT)}')
    return issues


def audit_raw_arm_literals() -> list[str]:
    issues = []
    for path in _active_python_files():
        if path in ALLOW_RAW_TOPIC_FILES:
            continue
        text = path.read_text(encoding='utf-8')
        if '/arm/' in text:
            issues.append(f'raw /arm/ literal remains in active file: {path.relative_to(ROOT)}')
    return issues


def audit_self_referential_fallbacks() -> list[str]:
    issues = []
    for path in _active_python_files():
        text = path.read_text(encoding='utf-8')
        if 'class TopicNames:' in text and '= TopicNames.' in text:
            issues.append(f'self-referential TopicNames fallback: {path.relative_to(ROOT)}')
        if 'class ServiceNames:' in text and '= ServiceNames.' in text:
            issues.append(f'self-referential ServiceNames fallback: {path.relative_to(ROOT)}')
    return issues




def audit_actionized_runtime_contracts() -> list[str]:
    issues = []
    task_node = SRC / 'arm_task_orchestrator' / 'arm_task_orchestrator' / 'task_orchestrator_node.py'
    bridge = ROOT / 'gateway' / 'ros_bridge.py'
    if 'ActionServer' not in task_node.read_text(encoding='utf-8'):
        issues.append('task orchestrator missing ActionServer support')
    if 'ActionClient' not in bridge.read_text(encoding='utf-8'):
        issues.append('gateway ros bridge missing ActionClient support')
    return issues


def audit_planner_executor_runtime_contracts() -> list[str]:
    issues = []
    planner = SRC / 'arm_motion_planner' / 'arm_motion_planner' / 'motion_planner_node.py'
    executor = SRC / 'arm_motion_executor' / 'arm_motion_executor' / 'motion_executor_node.py'
    planner_text = planner.read_text(encoding='utf-8')
    executor_text = executor.read_text(encoding='utf-8')
    if 'ActionServer' not in planner_text:
        issues.append('motion planner node missing ActionServer support')
    if 'TopicNames.INTERNAL_PLAN_TO_POSE' not in planner_text:
        issues.append('motion planner node missing INTERNAL_PLAN_TO_POSE runtime input')
    if 'ActionServer' not in executor_text:
        issues.append('motion executor node missing ActionServer support')
    if 'TopicNames.INTERNAL_EXECUTE_PLAN' not in executor_text:
        issues.append('motion executor node missing INTERNAL_EXECUTE_PLAN runtime input')
    return issues


def _active_package_xml_files() -> list[Path]:
    files = []
    for path in SRC.glob('*/package.xml'):
        if any(part in (DEPRECATED | EXPERIMENTAL) for part in path.parts):
            continue
        files.append(path)
    return files


def audit_active_package_dependencies() -> list[str]:
    issues = []
    for path in _active_package_xml_files():
        text = path.read_text(encoding='utf-8')
        if '<depend>arm_msgs</depend>' in text:
            issues.append(f'active package still depends on arm_msgs: {path.relative_to(ROOT)}')
        if '<depend>arm_vision</depend>' in text:
            issues.append(f'active package still depends on arm_vision: {path.relative_to(ROOT)}')
    return issues


def audit_active_python_package_metadata() -> list[str]:
    issues = []
    required = {
        'arm_common': ['<buildtool_depend>ament_python</buildtool_depend>', '<build_type>ament_python</build_type>', '<exec_depend>arm_backend_common</exec_depend>'],
        'arm_motion_planner': ['<buildtool_depend>ament_python</buildtool_depend>', '<build_type>ament_python</build_type>', '<exec_depend>arm_common</exec_depend>'],
        'arm_motion_executor': ['<buildtool_depend>ament_python</buildtool_depend>', '<build_type>ament_python</build_type>', '<exec_depend>arm_common</exec_depend>'],
    }
    for package, tokens in required.items():
        path = SRC / package / 'package.xml'
        text = path.read_text(encoding='utf-8')
        for token in tokens:
            if token not in text:
                issues.append(f'{package}/package.xml missing token: {token}')
        setup_path = SRC / package / 'setup.py'
        setup_text = setup_path.read_text(encoding='utf-8')
        for token in ('maintainer=', 'maintainer_email=', 'description=', 'license='):
            if token not in setup_text:
                issues.append(f'{package}/setup.py missing metadata field: {token}')
    return issues



def audit_readme_alignment() -> list[str]:
    issues = []
    root_readme = (ROOT / 'README.md').read_text(encoding='utf-8')
    backend_readme = (ROOT / 'backend' / 'README.backend.md').read_text(encoding='utf-8')
    for label, text in [('README.md', root_readme), ('backend/README.backend.md', backend_readme)]:
        if 'Ubuntu 22.04 LTS' not in text or 'Humble' not in text:
            issues.append(f'{label} missing validated environment matrix')
        if 'arm_vision' in text and 'arm_camera_driver' not in text:
            issues.append(f'{label} still advertises arm_vision as active main-chain component')
    return issues



def audit_environment_matrix() -> list[str]:
    issues = []
    root_readme = (ROOT / 'README.md').read_text(encoding='utf-8')
    gateway_readme = (ROOT / 'gateway' / 'README.md').read_text(encoding='utf-8')
    frontend_readme = (ROOT / 'frontend' / 'README.md').read_text(encoding='utf-8')
    backend_ws_readme = (ROOT / 'backend' / 'embodied_arm_ws' / 'README.md').read_text(encoding='utf-8')
    frontend_package = json.loads((ROOT / 'frontend' / 'package.json').read_text(encoding='utf-8'))
    engines = frontend_package.get('engines') or {}
    if (ROOT / '.nvmrc').read_text(encoding='utf-8').strip() != '22':
        issues.append('.nvmrc must pin Node.js 22')
    if (ROOT / '.python-version').read_text(encoding='utf-8').strip() != '3.10':
        issues.append('.python-version must pin Python 3.10 baseline')
    if engines.get('node') != '>=22 <23':
        issues.append('frontend/package.json engines.node must match README matrix')
    if str(frontend_package.get('packageManager', '')) != 'npm@10.9.2':
        issues.append('frontend/package.json packageManager must pin npm 10.9.2')
    for label, readme in [('README.md', root_readme), ('gateway/README.md', gateway_readme), ('frontend/README.md', frontend_readme), ('backend/embodied_arm_ws/README.md', backend_ws_readme)]:
        if 'Ubuntu 22.04 LTS' not in readme and label == 'frontend/README.md':
            continue
        if 'Ubuntu 22.04 LTS' not in readme:
            issues.append(f'{label} missing Ubuntu 22.04 LTS environment contract')
        if 'Node.js: **22.x**' not in readme:
            issues.append(f'{label} missing Node.js 22.x environment contract')
    if 'npm ci' not in frontend_readme:
        issues.append('frontend/README.md must use npm ci to match the validated install path')
    return issues


def audit_p0_p1_traceability() -> list[str]:
    issues = []
    path = ROOT / 'docs' / 'operations' / 'verification-and-release.md'
    compatibility_path = ROOT / 'docs' / 'evidence' / 'compatibility-regression.md'
    text = path.read_text(encoding='utf-8') if path.exists() else ''
    required = [
        'arm interfaces / mirror contract tests',
        'runtime lane truthfulness tests',
        'planner / executor / provider boundary tests',
        'launch / lane layout tests',
        'camera → perception → HMI frame summary tests',
        'reset fault / recover / maintenance closure tests',
    ]
    if not path.exists():
        issues.append('docs/operations/verification-and-release.md is missing')
        return issues
    for item in required:
        if item not in text:
            issues.append(f'verification traceability baseline missing item: {item}')
    quarantine_file = ROOT / 'backend' / 'embodied_arm_ws' / 'active_profile_quarantine.json'
    if quarantine_file.exists():
        ignored = json.loads(quarantine_file.read_text(encoding='utf-8')).get('ignoredTests', [])
        for entry in ignored:
            ignored_path = str(entry.get('path', '')).strip()
            if ignored_path and ignored_path in text:
                issues.append(f'canonical verification doc still cites quarantined compatibility test: {ignored_path}')
    if not compatibility_path.exists():
        issues.append('docs/evidence/compatibility-regression.md is missing')
    return issues



def audit_runtime_launch_split() -> list[str]:
    issues = []
    official = SRC / 'arm_bringup' / 'launch' / 'official_runtime.launch.py'
    sim = SRC / 'arm_bringup' / 'launch' / 'runtime_sim.launch.py'
    real = SRC / 'arm_bringup' / 'launch' / 'runtime_real.launch.py'
    hybrid = SRC / 'arm_bringup' / 'launch' / 'runtime_hybrid.launch.py'
    full_demo = SRC / 'arm_bringup' / 'launch' / 'full_demo.launch.py'
    alias_artifact = SRC / 'arm_bringup' / 'config' / 'runtime_lane_aliases.yaml'
    for path in (official, sim, real, hybrid):
        if not path.exists():
            issues.append(f'missing runtime launch file: {path.relative_to(ROOT)}')
    if issues:
        return issues
    official_text = official.read_text(encoding='utf-8')
    if 'Compatibility alias' not in official_text or 'runtime_sim.launch.py' not in official_text:
        issues.append('official_runtime.launch.py must be documented as a compatibility alias to runtime_sim.launch.py')
    factory = (SRC / 'arm_bringup' / 'arm_bringup' / 'launch_factory.py').read_text(encoding='utf-8')
    if 'RUNTIME_LANE_ALIAS_PATH' not in factory or 'COMPATIBILITY_RUNTIME_LANE_ALIASES' not in factory:
        issues.append('launch_factory.py must consume generated runtime_lane_aliases.yaml and expose compatibility alias maps')
    if not alias_artifact.exists():
        issues.append('runtime lane alias artifact missing: backend/embodied_arm_ws/src/arm_bringup/config/runtime_lane_aliases.yaml')
    else:
        try:
            alias_payload = yaml.safe_load(alias_artifact.read_text(encoding='utf-8')) or {}
        except Exception as exc:
            issues.append(f'failed to parse runtime_lane_aliases.yaml: {exc}')
        else:
            compatibility = alias_payload.get('compatibility', {}) if isinstance(alias_payload.get('compatibility'), dict) else {}
            official_runtime = compatibility.get('official_runtime', {}) if isinstance(compatibility.get('official_runtime'), dict) else {}
            if str(official_runtime.get('lane', '') or '').strip() != 'sim_preview':
                issues.append('runtime_lane_aliases.yaml missing official_runtime -> sim_preview compatibility mapping')
    demo_text = full_demo.read_text(encoding='utf-8') if full_demo.exists() else ''
    if full_demo.exists() and 'full_demo' not in demo_text:
        issues.append('full_demo launch should remain the demo entrypoint')
    return issues


def audit_validated_live_promotion_docs() -> list[str]:
    issues = []
    required_markers = [
        'validated_live_backbone_declared',
        'target_runtime_gate_passed',
        'hil_gate_passed',
        'release_checklist_signed',
    ]
    for rel_path in ('README.md', 'docs/operations/hil-and-promotion.md'):
        path = ROOT / rel_path
        text = path.read_text(encoding='utf-8') if path.exists() else ''
        if not path.exists():
            issues.append(f'{rel_path} is missing')
            continue
        for marker in required_markers:
            if marker not in text:
                issues.append(f'{rel_path} missing validated_live promotion marker: {marker}')
    return issues


def audit_release_checklist_alignment() -> list[str]:
    issues = []
    verification_doc = ROOT / 'docs' / 'operations' / 'verification-and-release.md'
    api_contract_doc = ROOT / 'docs' / 'interfaces' / 'api-contract.md'
    verification_text = verification_doc.read_text(encoding='utf-8') if verification_doc.exists() else ''
    api_contract_text = api_contract_doc.read_text(encoding='utf-8') if api_contract_doc.exists() else ''
    if not verification_doc.exists():
        issues.append('docs/operations/verification-and-release.md is missing')
        return issues
    if not api_contract_doc.exists():
        issues.append('docs/interfaces/api-contract.md is missing')
        return issues
    if 'servo-cartesian endpoint is explicitly disabled until dispatcher/transport closure' in verification_text:
        issues.append('verification/release doc still describes servo-cartesian as disabled')
    if 'servo-cartesian endpoint is wired through gateway validation, dispatcher mapping, and transport feedback closure' not in verification_text:
        issues.append('verification/release doc missing servo-cartesian closure gate')
    if '/api/hardware/servo-cartesian' not in api_contract_text:
        issues.append('canonical API contract missing /api/hardware/servo-cartesian endpoint')
    return issues


def audit_servo_contract_closure() -> list[str]:
    issues = []
    server = (ROOT / 'gateway' / 'routers' / 'hardware.py').read_text(encoding='utf-8')
    security = (ROOT / 'gateway' / 'security.py').read_text(encoding='utf-8')
    dispatcher = (SRC / 'arm_hardware_bridge' / 'arm_hardware_bridge' / 'hardware_command_dispatcher_node.py').read_text(encoding='utf-8')
    stm32 = (SRC / 'arm_hardware_bridge' / 'arm_hardware_bridge' / 'stm32_serial_node.py').read_text(encoding='utf-8')
    if "SERVO_CARTESIAN" not in dispatcher:
        issues.append('dispatcher missing SERVO_CARTESIAN command mapping')
    if '/api/hardware/servo-cartesian' not in server:
        issues.append('gateway hardware router missing servo cartesian endpoint')
    servo_bridge_tokens = ('await CTX.ros.servo_cartesian', "dispatch_runtime_command(command_plane='manual_control', action='hardware.servo_cartesian'")
    if 'validate_servo_command' not in server or not any(token in server for token in servo_bridge_tokens):
        issues.append('servo cartesian endpoint is not wired to gateway validation and ROS bridge')
    if 'SERVO_CARTESIAN' not in stm32:
        issues.append('STM32 simulated transport missing SERVO_CARTESIAN handling')
    if 'unsupported servo axis' not in security or 'delta must be within' not in security:
        issues.append('servo validation bounds missing from gateway security policy')
    return issues


def audit_calibration_activation_callback() -> list[str]:
    issues = []
    manager = (SRC / 'arm_calibration' / 'arm_calibration' / 'calibration_manager_node.py').read_text(encoding='utf-8')
    if 'def _activate_callback' not in manager:
        issues.append('calibration manager missing activation callback')
    if 'ServiceNames.ACTIVATE_CALIBRATION' not in manager:
        issues.append('calibration activation service not wired in node')
    return issues


def audit_doc_compatibility_mirrors() -> list[str]:
    issues = []
    manifest_path = DOC_COMPATIBILITY_MANIFEST_PATH
    if not manifest_path.exists():
        return ['docs/generated/doc_compatibility_manifest.json is missing']
    try:
        payload = json.loads(manifest_path.read_text(encoding='utf-8')) or {}
    except Exception as exc:  # pragma: no cover
        return [f'failed to parse doc compatibility manifest: {exc}']
    entries = payload.get('entries', []) if isinstance(payload.get('entries'), list) else []
    entry_map = {str(item.get('legacyPath', '') or ''): item for item in entries if isinstance(item, dict)}
    try:
        doc_outputs = render_doc_compatibility_outputs()
    except Exception as exc:
        return [f'doc compatibility mirror generation failed closed: {exc}']
    try:
        contract_outputs = render_contract_outputs()
    except Exception as exc:
        return [f'contract artifact generation failed closed: {exc}']
    generator_outputs = {
        'upper_computer/scripts/sync_doc_compatibility_mirrors.py': doc_outputs,
        'upper_computer/scripts/generate_contract_artifacts.py': contract_outputs,
    }
    expected_outputs = {
        path_obj.relative_to(ROOT).as_posix(): content
        for outputs in generator_outputs.values()
        for path_obj, content in outputs.items()
    }
    for legacy, item in sorted(entry_map.items()):
        canonical = str(item.get('canonicalPath', '') or '').strip()
        generator = str(item.get('generator', '') or '').strip()
        status = str(item.get('status', '') or '').strip()
        if not canonical:
            issues.append(f'doc compatibility manifest canonical missing: {legacy}')
            continue
        if status != 'generated compatibility mirror':
            issues.append(f'doc compatibility manifest status mismatch: {legacy}')
        if generator not in generator_outputs:
            issues.append(f'doc compatibility manifest generator unsupported: {legacy} -> {generator}')
            continue
        expected_content = expected_outputs.get(legacy)
        if expected_content is None:
            issues.append(f'doc compatibility manifest legacy path not produced by generator: {legacy}')
            continue
        path_obj = ROOT / legacy
        if not path_obj.exists():
            issues.append(f'doc compatibility mirror missing: {legacy}')
            continue
        current = path_obj.read_text(encoding='utf-8')
        if current != expected_content:
            issues.append(f'doc compatibility mirror drift: {legacy}')
        if 'generated compatibility mirror' not in current:
            issues.append(f'{legacy} must remain a generated compatibility mirror, not a pointer page')
        if canonical not in current and canonical.removeprefix('docs/') not in current:
            issues.append(f'{legacy} missing canonical reference: {canonical}')
    return issues


def audit_frontend_validation_evidence() -> list[str]:
    issues = []
    ledger_path = ROOT / 'artifacts' / 'release_gates' / 'frontend_validation_ledger.json'
    doc_path = ROOT / 'docs' / 'evidence' / 'frontend-validation-status.md'
    if not ledger_path.exists():
        issues.append('frontend validation ledger missing: artifacts/release_gates/frontend_validation_ledger.json')
        return issues
    try:
        payload = json.loads(ledger_path.read_text(encoding='utf-8')) or {}
    except Exception as exc:  # pragma: no cover
        issues.append(f'failed to parse frontend validation ledger: {exc}')
        return issues
    matrix = payload.get('matrix', []) if isinstance(payload.get('matrix'), list) else []
    expected_steps = {
        'frontend-deps',
        'frontend-typecheck-app',
        'frontend-typecheck-test',
        'frontend-unit',
        'frontend-build',
        'frontend-e2e',
    }
    actual_steps = {str(item.get('step', '') or '') for item in matrix if isinstance(item, dict)}
    if actual_steps != expected_steps:
        issues.append(f'frontend validation ledger step set drift: {sorted(actual_steps)} != {sorted(expected_steps)}')
    if str(payload.get('overallStatus', '') or '') not in {'passed', 'failed', 'blocked', 'partial', 'not_executed'}:
        issues.append('frontend validation ledger overallStatus must be one of passed/failed/blocked/partial/not_executed')
    if str(payload.get('sourceProfile', '') or '') == 'frontend_manual':
        issues.append('frontend validation ledger must not use legacy frontend_manual source profile')
    doc_text = doc_path.read_text(encoding='utf-8') if doc_path.exists() else ''
    if 'Machine-readable ledger' not in doc_text:
        issues.append('docs/evidence/frontend-validation-status.md missing machine-readable ledger reference')
    if '| Step | Group | Status | Required | Blocking Class | Log |' not in doc_text:
        issues.append('docs/evidence/frontend-validation-status.md missing validation matrix table')
    if '../../artifacts/release_gates/frontend_validation_ledger.json' not in doc_text:
        issues.append('docs/evidence/frontend-validation-status.md missing canonical frontend ledger path')
    issues.extend(check_frontend_validation_outputs())
    e2e_entry = next((item for item in matrix if isinstance(item, dict) and str(item.get('step', '') or '') == 'frontend-e2e'), None)
    environment = payload.get('environment', {}) if isinstance(payload.get('environment'), dict) else {}
    if 'playwrightBrowserContract' not in environment:
        issues.append('frontend validation ledger missing playwright browser environment contract')
    if isinstance(e2e_entry, dict):
        log_path_value = str(e2e_entry.get('logPath', '') or '').strip()
        if log_path_value:
            log_path = ROOT / log_path_value
            if log_path.exists():
                log_text = log_path.read_text(encoding='utf-8', errors='replace').lower()
                status = str(e2e_entry.get('status', 'not_executed') or 'not_executed')
                if '[frontend:e2e] skipped:' in log_text and status != 'skipped':
                    issues.append('frontend validation ledger marks frontend-e2e as non-skipped despite a skipped e2e log')
                if 'no usable chromium executable is available' in log_text and str(e2e_entry.get('blockingClass', '')) != 'infrastructure':
                    issues.append('frontend validation ledger must classify missing chromium as infrastructure blocking')
            elif bool(e2e_entry.get('logExists')):
                issues.append('frontend validation ledger claims frontend-e2e log exists but file is missing')
    build_entry = next((item for item in matrix if isinstance(item, dict) and str(item.get('step', '') or '') == 'frontend-build'), None)
    if isinstance(build_entry, dict):
        build_log_value = str(build_entry.get('logPath', '') or '').strip()
        if build_log_value:
            build_log = ROOT / build_log_value
            if build_log.exists():
                build_text = build_log.read_text(encoding='utf-8', errors='replace').lower()
                build_profile = str((environment.get('buildProfile', '') or '')).lower()
                build_status = str(build_entry.get('status', 'not_executed') or 'not_executed')
                if build_status == 'passed' and 'buildprofile=' in build_text and build_profile not in {'release', 'production'}:
                    issues.append('frontend validation ledger must expose the actual frontend build profile and standardize on release/production for release evidence')
    packaged_summary = _load_json_dict(ROOT / 'artifacts' / 'release_gates' / 'frontend_validation_artifacts' / 'verification_summary.json')
    packaged_steps = packaged_summary.get('stepStatuses', {}) if isinstance(packaged_summary.get('stepStatuses'), dict) else {}
    for item in matrix:
        if not isinstance(item, dict):
            continue
        step_name = str(item.get('step', '') or '')
        ledger_status = str(item.get('status', 'not_executed') or 'not_executed')
        packaged_status = str(packaged_steps.get(step_name, 'not_executed') or 'not_executed')
        if packaged_status != ledger_status:
            issues.append(f'frontend packaged summary drift for {step_name}: {packaged_status} != {ledger_status}')
    packaged_overall = str(packaged_summary.get('overallStatus', 'not_executed') or 'not_executed')
    ledger_overall = str(payload.get('overallStatus', 'not_executed') or 'not_executed')
    if packaged_overall != ledger_overall:
        issues.append('frontend packaged summary overallStatus drift from ledger overallStatus')
    return issues


def audit_release_manifest() -> list[str]:
    script_path = ROOT / 'scripts' / 'package_release.py'
    if not script_path.exists():
        return ['upper-computer release packager missing: scripts/package_release.py']
    spec = importlib_util.spec_from_file_location('package_release_audit', script_path)
    if spec is None or spec.loader is None:  # pragma: no cover
        return ['failed to load release packager for audit']
    module = importlib_util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return list(module.check_manifest(root=ROOT))


def audit_split_release_manifest() -> list[str]:
    script_path = ROOT.parent / 'scripts' / 'package_split_release.py'
    if not script_path.exists():
        return ['top-level split release packager missing: ../scripts/package_split_release.py']
    spec = importlib_util.spec_from_file_location('package_split_release_audit', script_path)
    if spec is None or spec.loader is None:  # pragma: no cover
        return ['failed to load top-level split release packager for audit']
    module = importlib_util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return list(module.check_manifest(root=ROOT.parent))


def audit_generated_contract_artifacts() -> list[str]:
    issues = []
    generated = [
        ROOT / 'docs' / 'generated' / 'runtime_contract_manifest.json',
        ROOT / 'docs' / 'generated' / 'runtime_contract_summary.md',
        ROOT / 'docs' / 'generated' / 'runtime_acceptance_matrix.md',
        ROOT / 'docs' / 'CONTRACT_INDEX.md',
        ROOT / 'docs' / 'ROS2_INTERFACE_INDEX.md',
    ]
    try:
        expected_outputs = render_contract_outputs()
    except Exception as exc:
        return [f'generated contract artifact render failed closed: {exc}']
    for path in generated:
        if not path.exists():
            issues.append(f'missing generated contract artifact: {path.relative_to(ROOT)}')
            continue
        expected = expected_outputs.get(path)
        if expected is not None and path.read_text(encoding='utf-8') != expected:
            issues.append(f'generated contract artifact drift: {path.relative_to(ROOT)}')
    return issues


def audit_ros_validation_assets() -> list[str]:
    issues = []
    workflow = (ROOT / '.github' / 'workflows' / 'ci.yml').read_text(encoding='utf-8') if (ROOT / '.github' / 'workflows' / 'ci.yml').exists() else ''
    if 'ros-humble:' not in workflow:
        issues.append('ci workflow missing ros-humble job')
    if 'colcon build --symlink-install' not in workflow:
        issues.append('ci workflow missing colcon build step')
    if 'test_ros_launch_smoke.py' not in workflow or 'test_gateway_dispatcher_feedback_roundtrip.py' not in workflow:
        issues.append('ci workflow missing ROS smoke / round-trip test execution')
    if 'runs-on: ubuntu-22.04' not in workflow:
        issues.append('ci workflow not pinned to ubuntu-22.04')
    if 'npm install -g npm@10.9.2' not in workflow:
        issues.append('ci workflow missing npm 10.9.2 pin for frontend job')
    for path in [
        ROOT / 'backend' / 'embodied_arm_ws' / 'tests' / 'test_ros_launch_smoke.py',
        ROOT / 'backend' / 'embodied_arm_ws' / 'tests' / 'test_gateway_dispatcher_feedback_roundtrip.py',
        ROOT / 'scripts' / 'ros_target_validation.sh',
    ]:
        if not path.exists():
            issues.append(f'missing ROS validation asset: {path.relative_to(ROOT)}')
    backend_ws_readme = (ROOT / 'backend' / 'embodied_arm_ws' / 'README.md').read_text(encoding='utf-8') if (ROOT / 'backend' / 'embodied_arm_ws' / 'README.md').exists() else ''
    if 'runtime_sim.launch.py' not in backend_ws_readme:
        issues.append('backend workspace README missing runtime_sim launch entrypoint')
    if 'official_runtime.launch.py' not in backend_ws_readme or 'compatibility alias to the `sim_preview` lane' not in backend_ws_readme:
        issues.append('backend workspace README must describe official_runtime.launch.py as a compatibility alias to the sim_preview lane')
    return issues

def audit_python_parse() -> list[str]:
    issues = []
    for path in _active_python_files():
        try:
            ast.parse(path.read_text(encoding='utf-8'))
        except SyntaxError as exc:
            issues.append(f'syntax error in {path.relative_to(ROOT)}: {exc}')
    return issues


def audit_active_profile_consistency() -> list[str]:
    issues = []
    path = ROOT / 'scripts' / 'check_active_profile_consistency.py'
    if not path.exists():
        return ['scripts/check_active_profile_consistency.py is missing']
    try:
        from scripts.check_active_profile_consistency import validate_active_profile
    except Exception as exc:  # pragma: no cover
        return [f'failed to import active profile consistency checker: {exc}']
    issues.extend(validate_active_profile())
    return issues




def audit_runtime_implementer_docs() -> list[str]:
    script = ROOT / 'scripts' / 'check_runtime_implementer_docs.py'
    if not script.exists():
        return ['missing runtime implementer doc gate script']
    result = __import__('subprocess').run([sys.executable, str(script)], cwd=ROOT, capture_output=True, text=True, check=False)
    if result.returncode == 0:
        return []
    output = (result.stdout + result.stderr).strip().splitlines()
    return [line for line in output if line.strip()] or ['runtime implementer docs check failed']

def audit_runtime_authority_consistency() -> list[str]:
    try:
        validate_runtime_authority_consistency(load_runtime_authority())
    except RuntimeError as exc:
        return [f'runtime authority consistency failed: {exc}']
    return []


def audit_frontend_lockfile_registry() -> list[str]:
    issues = []
    lockfile = ROOT / 'frontend' / 'package-lock.json'
    text = lockfile.read_text(encoding='utf-8') if lockfile.exists() else ''
    for token in (
        'packages.applied-caas-gateway1.internal.api.openai.org',
        'artifactory/api/npm',
        'reader:',
        '_authToken',
    ):
        if token in text:
            issues.append(f'frontend/package-lock.json contains forbidden registry material: {token}')
    return issues




def audit_frontend_release_build_guard() -> list[str]:
    issues = []
    guard = ROOT / 'frontend' / 'scripts' / 'assert-build-mode.mjs'
    package_json = ROOT / 'frontend' / 'package.json'
    if not guard.exists():
        return ['frontend release build guard missing: frontend/scripts/assert-build-mode.mjs']
    try:
        payload = json.loads(package_json.read_text(encoding='utf-8'))
    except Exception as exc:  # pragma: no cover
        return [f'failed to parse frontend/package.json: {exc}']
    scripts = payload.get('scripts') or {}
    build_script = str(scripts.get('build', '') or '')
    if 'assert-build-mode.mjs' not in build_script:
        issues.append('frontend/package.json build script missing assert-build-mode.mjs guard')
    guard_text = guard.read_text(encoding='utf-8')
    for token in ('VITE_ENABLE_MOCK', 'VITE_API_MOCK_MODE', 'release', 'production'):
        if token not in guard_text:
            issues.append(f'frontend build guard missing token: {token}')
    return issues



def clean_hygiene_residue() -> None:
    for path in ROOT.rglob('*'):
        if any(part in {'node_modules', '.pio', 'build', 'install', 'log', '.venv'} for part in path.parts):
            continue
        if (
            path.name.endswith('.pyc')
            or path.name.endswith('.tsbuildinfo')
            or '__pycache__' in path.parts
            or '.pytest_cache' in path.parts
        ):
            if path.is_dir():
                for child in sorted(path.rglob('*'), reverse=True):
                    if child.is_file() or child.is_symlink():
                        child.unlink(missing_ok=True)
                for child in sorted(path.rglob('*'), reverse=True):
                    if child.is_dir():
                        child.rmdir()
                path.rmdir()
            else:
                path.unlink(missing_ok=True)




def audit_runtime_execution_contracts() -> list[str]:
    issues = []
    topic_names = (SRC / 'arm_common' / 'arm_common' / 'topic_names.py').read_text(encoding='utf-8')
    motion_executor = (SRC / 'arm_motion_executor' / 'arm_motion_executor' / 'motion_executor_node.py').read_text(encoding='utf-8')
    dispatcher = (SRC / 'arm_hardware_bridge' / 'arm_hardware_bridge' / 'hardware_command_dispatcher_node.py').read_text(encoding='utf-8')
    launch_factory = (SRC / 'arm_bringup' / 'arm_bringup' / 'launch_factory.py').read_text(encoding='utf-8')
    runtime_profiles = (SRC / 'arm_bringup' / 'config' / 'runtime_profiles.yaml').read_text(encoding='utf-8')
    if 'FAULT_REPORT' not in topic_names:
        issues.append('TopicNames missing FAULT_REPORT contract')
    if 'TopicNames.SYSTEM_FAULT' in motion_executor:
        issues.append('motion executor still references TopicNames.SYSTEM_FAULT')
    if 'create_subscription(HardwareState, TopicNames.HARDWARE_STATE' not in motion_executor:
        issues.append('motion executor must consume typed HardwareState topic')
    if 'create_subscription(FaultReport, TopicNames.FAULT_REPORT' not in motion_executor:
        issues.append('motion executor must consume typed FaultReport topic')
    if "'command_id'" not in dispatcher:
        issues.append('dispatcher feedback must carry command_id correlation')
    if "'forward_hardware_commands': forward_hardware_commands" not in launch_factory:
        issues.append('launch factory missing motion executor forwarding parameter wiring')
    for token in ('forward_hardware_commands:', 'frame_ingress_mode:', 'hardware_execution_mode:'):
        if token not in runtime_profiles:
            issues.append(f'runtime profile missing lane field: {token}')
    return issues

def audit_package_support_alignment() -> list[str]:
    issues = []
    overview = (ROOT / 'docs' / 'architecture' / 'system-overview.md').read_text(encoding='utf-8') if (ROOT / 'docs' / 'architecture' / 'system-overview.md').exists() else ''
    if '`arm_esp32_gateway` | runtime-core | yes' not in overview:
        issues.append('docs/architecture/system-overview.md must classify arm_esp32_gateway as runtime-core and active-lane included')
    if 'Runtime Core representative packages' not in overview or 'arm_esp32_gateway' not in overview:
        issues.append('docs/architecture/system-overview.md must classify arm_esp32_gateway inside Runtime Core representative packages')
    if 'Experimental representative packages' not in overview or '`arm_hmi`' not in overview:
        issues.append('docs/architecture/system-overview.md must leave arm_hmi in the Experimental representative packages bucket')
    return issues



def audit_runtime_api_contract_alignment() -> list[str]:
    issues = []
    openapi_path = ROOT / 'gateway' / 'openapi' / 'runtime_api.yaml'
    generated_client = ROOT / 'frontend' / 'src' / 'api' / 'generated' / 'index.ts'
    system_service = ROOT / 'frontend' / 'src' / 'services' / 'api' / 'system.ts'
    task_service = ROOT / 'frontend' / 'src' / 'services' / 'api' / 'task.ts'
    if not openapi_path.exists():
        return ['runtime_api.yaml missing']
    try:
        payload = yaml.safe_load(openapi_path.read_text(encoding='utf-8')) or {}
    except Exception as exc:  # pragma: no cover
        return [f'failed to parse runtime_api.yaml: {exc}']
    paths = payload.get('paths', {}) if isinstance(payload, dict) else {}
    try:
        from fastapi.routing import APIRoute
        from gateway.server import app
        public_routes = {
            route.path
            for route in app.routes
            if isinstance(route, APIRoute)
            and not route.path.startswith('/openapi')
            and not route.path.startswith('/docs')
            and not route.path.startswith('/redoc')
            and 'WS' not in ''.join(route.methods or set())
        }
    except Exception as exc:  # pragma: no cover
        return [f'failed to import gateway app for route audit: {exc}']
    if set(paths.keys()) != public_routes:
        issues.append('runtime_api.yaml path set does not match public gateway route set')

    task_start = paths.get('/api/task/start', {}).get('post', {}) if isinstance(paths.get('/api/task/start', {}), dict) else {}
    request_schema = (((task_start.get('requestBody') or {}).get('content') or {}).get('application/json') or {}).get('schema')
    if request_schema != {'$ref': '#/components/schemas/StartTaskRequest'}:
        issues.append('runtime_api.yaml missing StartTaskRequest request schema for /api/task/start')
    readiness = paths.get('/api/system/readiness', {}).get('get', {}) if isinstance(paths.get('/api/system/readiness', {}), dict) else {}
    if '200' not in (readiness.get('responses', {}) or {}):
        issues.append('runtime_api.yaml missing 200 response for /api/system/readiness')

    generated_text = generated_client.read_text(encoding='utf-8') if generated_client.exists() else ''
    if 'export class RuntimeApiError extends Error' not in generated_text:
        issues.append('generated runtime API client missing RuntimeApiError class')
    if 'export type StartTaskDecision' not in generated_text:
        issues.append('generated runtime API client missing StartTaskDecision type')
    if "return await unwrapResponse<RuntimeReadiness>(apiClient.get<ApiResponse<RuntimeReadiness>>(routes.systemReadiness));" not in generated_text:
        issues.append('generated runtime API client must expose typed systemReadiness request through apiClient')
    if "return await unwrapResponse<StartTaskDecision>(apiClient.post<ApiResponse<StartTaskDecision>>(routes.taskStart, payload));" not in generated_text:
        issues.append('generated runtime API client must expose typed taskStart request through apiClient')
    if 'throw asRuntimeApiError(error);' not in generated_text:
        issues.append('generated runtime API client must normalize transport errors into RuntimeApiError')
    if "from '@/api/generated'" not in system_service.read_text(encoding='utf-8'):
        issues.append('frontend system service must consume generated runtime API client')
    if "from '@/api/generated'" not in task_service.read_text(encoding='utf-8'):
        issues.append('frontend task service must consume generated runtime API client')
    return issues


def audit_repository_gate_evidence() -> list[str]:
    issues = []
    release_model = ROOT / 'scripts' / 'release_state_model.py'
    verify_repo = ROOT / 'scripts' / 'verify_repository.py'
    summary_path = ROOT / 'artifacts' / 'repository_validation' / 'repo' / 'verification_summary.json'
    release_text = release_model.read_text(encoding='utf-8') if release_model.exists() else ''
    verify_text = verify_repo.read_text(encoding='utf-8') if verify_repo.exists() else ''
    if 'verification_summary.json' not in release_text:
        issues.append('release_state_model.py must derive repoGate from verification_summary.json')
    if '_write_verification_summary' not in verify_text:
        issues.append('verify_repository.py must emit verification_summary.json')
    if "'generatedBy': 'scripts/verify_repository.py'" not in verify_text:
        issues.append('verification summary must record generatedBy=scripts/verify_repository.py')
    if "'overallStatus': overall_status" not in verify_text:
        issues.append('verification summary must record overallStatus')
    if "'requiredSteps': required_steps" not in verify_text:
        issues.append('verification summary must record requiredSteps')
    if "'stepStatuses': step_statuses" not in verify_text:
        issues.append('verification summary must record stepStatuses')
    payload = _load_json_dict(summary_path)
    if payload:
        generated_by = str(payload.get('generatedBy', '') or '')
        if generated_by != 'scripts/verify_repository.py':
            issues.append('artifacts/repository_validation/repo/verification_summary.json must be produced by scripts/verify_repository.py')
        if 'snapshotSource' in payload:
            issues.append('artifacts/repository_validation/repo/verification_summary.json must not be a materialized snapshot')
    return issues


def audit_runtime_entrypoint_hardening() -> list[str]:
    issues = []
    launch_factory = ROOT / 'backend' / 'embodied_arm_ws' / 'src' / 'arm_bringup' / 'arm_bringup' / 'launch_factory.py'
    retired_wrapper = ROOT / 'backend' / 'embodied_arm_ws' / 'src' / 'arm_bringup' / 'launch' / 'runtime_real_authoritative.launch.py'
    migration_doc = ROOT / 'docs' / 'archive' / 'control-lane-migration.md'
    text = launch_factory.read_text(encoding='utf-8') if launch_factory.exists() else ''
    wrapper_text = retired_wrapper.read_text(encoding='utf-8') if retired_wrapper.exists() else ''
    migration_text = migration_doc.read_text(encoding='utf-8') if migration_doc.exists() else ''
    if "build_runtime_launch_description('live_control')" in wrapper_text:
        issues.append('runtime_real_authoritative wrapper still bypasses legacy-alias retirement by launching live_control directly')
    if "build_runtime_launch_description('real_authoritative')" not in wrapper_text:
        issues.append('runtime_real_authoritative wrapper must resolve through the retired alias name so opt-in gating stays active')
    if 'EMBODIED_ARM_ALLOW_LEGACY_LIVE_ALIASES=true' not in wrapper_text:
        issues.append('runtime_real_authoritative wrapper must document the temporary migration environment opt-in')
    if 'EMBODIED_ARM_ALLOW_LEGACY_LIVE_ALIASES=true' not in migration_text:
        issues.append('docs/archive/control-lane-migration.md must describe the retired wrapper opt-in requirement')
    if '_allow_generated_runtime_fallback(' in text:
        issues.append('launch_factory must not reference the removed generated-runtime fallback helper')
    return issues


def audit_active_overlay_isolation() -> list[str]:
    issues = []
    overlay_script = ROOT / 'scripts' / 'materialize_active_ros_overlay.py'
    makefile = ROOT / 'Makefile'
    ci = ROOT / '.github' / 'workflows' / 'ci.yml'
    root_gitignore = ROOT.parent / '.gitignore'
    workspace_gitignore = ROOT / '.gitignore'
    script_text = overlay_script.read_text(encoding='utf-8') if overlay_script.exists() else ''
    makefile_text = makefile.read_text(encoding='utf-8') if makefile.exists() else ''
    ci_text = ci.read_text(encoding='utf-8') if ci.exists() else ''
    root_gitignore_text = root_gitignore.read_text(encoding='utf-8') if root_gitignore.exists() else ''
    workspace_gitignore_text = workspace_gitignore.read_text(encoding='utf-8') if workspace_gitignore.exists() else ''
    overlay_prefix = Path('backend/embodied_arm_ws/.active_overlay')
    if not overlay_script.exists():
        issues.append('scripts/materialize_active_ros_overlay.py is missing')
        return issues
    for token in ('active_workspace_packages', 'dependency_closure', '.active_overlay'):
        if token not in script_text:
            issues.append(f'active overlay script missing token: {token}')
    if 'materialize_active_ros_overlay.py --print-root' not in makefile_text:
        issues.append('Makefile ros-build/ros-smoke entrypoints must use the active ROS overlay workspace')
    if "find $(ROOT) -type d -name '.active_overlay' -prune -exec rm -rf {} +" not in makefile_text:
        issues.append('Makefile clean must remove the generated .active_overlay workspace')
    if 'materialize_active_ros_overlay.py --print-root' not in ci_text:
        issues.append('CI backend build/smoke steps must use the active ROS overlay workspace')
    if 'rosdep install --from-paths "$ACTIVE_OVERLAY/src" --ignore-src -r -y --rosdistro humble' not in ci_text:
        issues.append('CI backend dependency installation must resolve rosdep against the active ROS overlay src tree')
    if "upper_computer/backend/embodied_arm_ws/.active_overlay/" not in root_gitignore_text:
        issues.append('root .gitignore must ignore the generated active overlay workspace')
    if '.active_overlay/' not in workspace_gitignore_text:
        issues.append('upper_computer/.gitignore must ignore the generated active overlay workspace')
    if overlay_prefix not in RELEASE_EXCLUDE_PREFIXES:
        issues.append('release packaging must exclude backend/embodied_arm_ws/.active_overlay')
    if not release_should_skip(overlay_prefix / 'overlay_packages.txt'):
        issues.append('release packaging must skip generated active overlay metadata files')
    return issues


def audit_runtime_truth_fail_fast() -> list[str]:
    issues = []
    launch_factory = ROOT / 'backend' / 'embodied_arm_ws' / 'src' / 'arm_bringup' / 'arm_bringup' / 'launch_factory.py'
    backend_factory = ROOT / 'backend' / 'embodied_arm_ws' / 'src' / 'arm_motion_planner' / 'arm_motion_planner' / 'backend_factory.py'
    launch_text = launch_factory.read_text(encoding='utf-8') if launch_factory.exists() else ''
    backend_text = backend_factory.read_text(encoding='utf-8') if backend_factory.exists() else ''
    if 'return dict(RUNTIME_LANE_SPECS)' in launch_text:
        issues.append('launch_factory still silently falls back to built-in runtime lane specs')
    if 'profiles = dict(_BUILTIN_PROFILES)' in backend_text:
        issues.append('backend_factory still silently falls back to built-in planning backend profiles')
    return issues

def audit_validated_live_evidence() -> list[str]:
    issues = []
    if not VALIDATED_LIVE_EVIDENCE.exists():
        return ['validated_live evidence manifest missing']
    evidence_manifest = load_validated_live_evidence(VALIDATED_LIVE_EVIDENCE)
    evidence = evidence_manifest.get('evidence', {}) if isinstance(evidence_manifest.get('evidence'), dict) else {}
    for marker in ('target_runtime_gate_passed', 'hil_gate_passed', 'release_checklist_signed'):
        item = evidence.get(marker, {}) if isinstance(evidence.get(marker), dict) else {}
        artifact = str(item.get('artifact', '') or '').strip()
        if not artifact:
            issues.append(f'validated_live evidence missing artifact path: {marker}')
            continue
        if not (ROOT / artifact).exists():
            issues.append(f'validated_live evidence artifact missing: {marker} -> {artifact}')
            continue
        issues.extend(f'validated_live evidence inconsistency: {marker} -> {issue}' for issue in validated_live_artifact_issues(marker, evidence_manifest))
    if not RUNTIME_PROMOTION_RECEIPTS.exists():
        issues.append('runtime_promotion_receipts.yaml is missing')
        return issues
    try:
        receipts = yaml.safe_load(RUNTIME_PROMOTION_RECEIPTS.read_text(encoding='utf-8')) or {}
    except Exception as exc:  # pragma: no cover
        issues.append(f'failed to parse runtime_promotion_receipts.yaml: {exc}')
        return issues
    if not isinstance(receipts, dict):
        issues.append('runtime_promotion_receipts.yaml must be a mapping')
        return issues
    status = evaluate_promotion_receipt(
        receipts.get('validated_live', {}) if isinstance(receipts, dict) else {},
        authority=load_runtime_authority(),
        evidence_manifest=evidence_manifest,
    )
    generated = receipts.get('validated_live', {}) if isinstance(receipts.get('validated_live'), dict) else {}
    if bool(generated.get('effective', False)) != bool(status.effective):
        issues.append('validated_live effective flag drift between receipt yaml and evaluated truth')
    if list(generated.get('missing_evidence', [])) != list(status.missing):
        issues.append('validated_live missing_evidence drift between receipt yaml and evaluated truth')
    return issues


def audit_release_gate_consistency() -> list[str]:
    issues = []
    gate_report_path = ROOT / 'artifacts' / 'release_gates' / 'target_runtime_gate.json'
    release_evidence_path = ROOT / 'artifacts' / 'release_gates' / 'release_evidence.json'
    frontend_ledger_path = ROOT / 'artifacts' / 'release_gates' / 'frontend_validation_ledger.json'
    expected_paths = {
        'artifacts/repository_validation/repo/verification_summary.json',
        'artifacts/target_env_report.json',
        'artifacts/release_gates/runtime_baseline_report.json',
        'artifacts/release_gates/validated_live_hil_gate.json',
        'artifacts/release_gates/validated_live_release_checklist_gate.json',
    }
    authoritative = _authoritative_release_gate_report()
    gate_payload = _load_json_dict(gate_report_path)
    for field in ('repoGate', 'targetGate', 'hilGate', 'releaseChecklistGate', 'releaseGate'):
        if str(gate_payload.get(field, 'not_executed') or 'not_executed') != str(authoritative.get(field, 'not_executed') or 'not_executed'):
            issues.append(f'target_runtime_gate.json drift for {field}')
    release_evidence = _load_json_dict(release_evidence_path)
    issues.extend(_audit_release_evidence_file_provenance(release_evidence))
    gate_summary = release_evidence.get('gateSummary', {}) if isinstance(release_evidence.get('gateSummary'), dict) else {}
    for field in ('repoGate', 'targetGate', 'hilGate', 'releaseChecklistGate', 'releaseGate'):
        if str(gate_summary.get(field, 'not_executed') or 'not_executed') != str(authoritative.get(field, 'not_executed') or 'not_executed'):
            issues.append(f'release_evidence.json gateSummary drift for {field}')
    evidence = release_evidence.get('evidence', []) if isinstance(release_evidence.get('evidence'), list) else []
    recorded_paths = {str(item.get('path', '') or '') for item in evidence if isinstance(item, dict)}
    for required in sorted(expected_paths):
        if required not in recorded_paths:
            issues.append(f'release_evidence.json missing supporting evidence entry: {required}')
    frontend_ledger = _load_json_dict(frontend_ledger_path)
    frontend_status = str(frontend_ledger.get('overallStatus', 'not_executed') or 'not_executed')
    if frontend_status in {'failed', 'blocked'} and str(authoritative.get('releaseGate', 'not_executed') or 'not_executed') == 'passed':
        issues.append('release gate must not pass when standardized frontend validation is blocked/failed')
    evidence_manifest = load_validated_live_evidence(VALIDATED_LIVE_EVIDENCE)
    evidence_payload = evidence_manifest.get('evidence', {}) if isinstance(evidence_manifest.get('evidence'), dict) else {}
    target_gate_rel = 'artifacts/release_gates/target_runtime_gate.json'
    for marker in ('hil_gate_passed', 'release_checklist_signed'):
        item = evidence_payload.get(marker, {}) if isinstance(evidence_payload.get(marker), dict) else {}
        gate_report = str(item.get('gate_report', '') or '').strip()
        if gate_report == target_gate_rel:
            issues.append(f'validated_live evidence gate_report must not self-reference target_runtime_gate.json: {marker}')
    target_env = _load_json_dict(ROOT / 'artifacts' / 'target_env_report.json')
    facts = target_env.get('facts', {}) if isinstance(target_env.get('facts'), dict) else {}
    workspace_dir = str(facts.get('workspaceDir', '') or '')
    if workspace_dir.startswith('/mnt/data/'):
        issues.append('target_env_report.json must not embed build-machine workspaceDir absolute paths')
    baseline = _load_json_dict(ROOT / 'artifacts' / 'release_gates' / 'runtime_baseline_report.json')
    baseline_report = baseline.get('report', {}) if isinstance(baseline.get('report'), dict) else {}
    observability_root = str(baseline_report.get('observabilityRoot', '') or '')
    if observability_root.startswith('/mnt/data/'):
        issues.append('runtime_baseline_report.json must not embed build-machine observabilityRoot absolute paths')
    baseline_files = baseline_report.get('files', {}) if isinstance(baseline_report.get('files'), dict) else {}
    if any(str(value or '').startswith('/mnt/data/') for value in baseline_files.values()):
        issues.append('runtime_baseline_report.json must not embed build-machine observability file absolute paths')
    split_manifest_path = ROOT.parent / 'artifacts' / 'split_release_manifest.json'
    if split_manifest_path.exists():
        split_manifest = _load_json_dict(split_manifest_path)
        files = split_manifest.get('files', []) if isinstance(split_manifest.get('files'), list) else []
        if 'upper_computer/artifacts/release_gates/runtime_baseline_repo_sample.json' in files:
            issues.append('split release manifest must not ship runtime_baseline_repo_sample.json')
    return issues


def audit_delivery_artifact_residue() -> list[str]:
    issues = []
    if DELIVERY_REPORT.exists():
        issues.append('root DELIVERY_REPORT.md must not be shipped in final delivery tree')
    for archive in sorted(ROOT.rglob('*.zip')):
        relative = archive.relative_to(ROOT)
        if release_should_skip(relative):
            continue
        issues.append(f'nested zip archive present in delivery tree: {relative.as_posix()}')
    return issues


def audit_repository_hygiene() -> list[str]:
    issues = []
    for path in ROOT.rglob('*'):
        relative = path.relative_to(ROOT)
        if any(part in {'node_modules', '.pio', 'build', 'install', 'log', '.venv', 'dist'} for part in path.parts):
            continue
        if (
            path.name.endswith('.pyc')
            or path.name.endswith('.pyo')
            or path.name.endswith('.tsbuildinfo')
            or '__pycache__' in path.parts
            or '.pytest_cache' in path.parts
        ):
            if release_should_skip(relative):
                continue
            issues.append(f'repository hygiene violation: {relative}')
    required_packaging_excludes = {Path('frontend/node_modules'), Path('frontend/dist')}
    missing_packaging_excludes = sorted(required_packaging_excludes - set(RELEASE_EXCLUDE_PREFIXES))
    for prefix in missing_packaging_excludes:
        issues.append(f'release packaging missing required exclude prefix: {prefix.as_posix()}')
    for prefix in sorted(required_packaging_excludes):
        absolute_prefix = ROOT / prefix
        if not absolute_prefix.exists():
            continue
        if not release_should_skip(prefix):
            issues.append(f'release packaging does not skip generated directory prefix: {prefix.as_posix()}')
            continue
        for candidate in absolute_prefix.rglob('*'):
            if candidate.is_dir():
                continue
            relative_candidate = candidate.relative_to(ROOT)
            if not release_should_skip(relative_candidate):
                issues.append(f'release packaging does not skip generated file: {relative_candidate.as_posix()}')
                break
    return issues

def main(argv: list[str] | None = None) -> int:
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--clean', action='store_true', help='Clean hygiene residue before auditing. Default is non-mutating audit.')
    args = parser.parse_args(argv)
    if args.clean:
        clean_hygiene_residue()
    checks = [
        ('arm_msgs import leak', audit_arm_msgs_imports),
        ('raw /arm literal leak', audit_raw_arm_literals),
        ('self-referential fallback', audit_self_referential_fallbacks),
        ('actionized runtime contracts', audit_actionized_runtime_contracts),
        ('planner executor runtime contracts', audit_planner_executor_runtime_contracts),
        ('active profile consistency', audit_active_profile_consistency),
        ('runtime authority consistency', audit_runtime_authority_consistency),
        ('runtime implementer docs', audit_runtime_implementer_docs),
        ('public interface ownership', validate_public_interface_ownership),
        ('runtime launch split', audit_runtime_launch_split),
        ('validated live promotion docs', audit_validated_live_promotion_docs),
        ('release checklist alignment', audit_release_checklist_alignment),
        ('servo contract closure', audit_servo_contract_closure),
        ('calibration activation callback', audit_calibration_activation_callback),
        ('active package deps', audit_active_package_dependencies),
        ('readme alignment', audit_readme_alignment),
        ('environment matrix', audit_environment_matrix),
        ('package support alignment', audit_package_support_alignment),
        ('p0 p1 traceability', audit_p0_p1_traceability),
        ('doc compatibility mirrors', audit_doc_compatibility_mirrors),
        ('frontend validation evidence', audit_frontend_validation_evidence),
        ('generated contract artifacts', audit_generated_contract_artifacts),
        ('release manifest', audit_release_manifest),
        ('split release manifest', audit_split_release_manifest),
        ('runtime execution contracts', audit_runtime_execution_contracts),
        ('ros validation assets', audit_ros_validation_assets),
        ('runtime api contract alignment', audit_runtime_api_contract_alignment),
        ('repository gate evidence', audit_repository_gate_evidence),
        ('runtime entrypoint hardening', audit_runtime_entrypoint_hardening),
        ('active overlay isolation', audit_active_overlay_isolation),
        ('runtime truth fail fast', audit_runtime_truth_fail_fast),
        ('frontend lockfile registry', audit_frontend_lockfile_registry),
        ('frontend release build guard', audit_frontend_release_build_guard),
        ('validated live evidence', audit_validated_live_evidence),
        ('release gate consistency', audit_release_gate_consistency),
        ('delivery artifact residue', audit_delivery_artifact_residue),
        ('repository hygiene', audit_repository_hygiene),
        ('python parse', audit_python_parse),
    ]
    failures = []
    for name, fn in checks:
        issues = fn()
        if issues:
            failures.append((name, issues))
    if failures:
        print('FINAL AUDIT FAILED')
        for name, issues in failures:
            print(f'[{name}]')
            for issue in issues:
                print(' -', issue)
        return 1
    print('FINAL AUDIT PASSED')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
