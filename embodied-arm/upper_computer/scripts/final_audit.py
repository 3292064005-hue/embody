from __future__ import annotations

import ast
import json
import yaml
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
from runtime_authority import load_runtime_authority, load_validated_live_evidence, evaluate_promotion_receipt, validate_runtime_authority_consistency
from scripts.check_public_interface_ownership import validate_public_interface_ownership

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
    path = ROOT / 'docs' / 'P0_P1_TRACEABILITY.md'
    compatibility_path = ROOT / 'docs' / 'COMPATIBILITY_REGRESSION_EVIDENCE.md'
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
        issues.append('docs/P0_P1_TRACEABILITY.md is missing')
        return issues
    for item in required:
        if item not in text:
            issues.append(f'traceability doc missing item: {item}')
    quarantine_file = ROOT / 'backend' / 'embodied_arm_ws' / 'active_profile_quarantine.json'
    if quarantine_file.exists():
        ignored = json.loads(quarantine_file.read_text(encoding='utf-8')).get('ignoredTests', [])
        for entry in ignored:
            ignored_path = str(entry.get('path', '')).strip()
            if ignored_path and ignored_path in text:
                issues.append(f'active traceability doc still cites quarantined compatibility test: {ignored_path}')
    if not compatibility_path.exists():
        issues.append('docs/COMPATIBILITY_REGRESSION_EVIDENCE.md is missing')
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
    for rel_path in ('README.md', 'docs/VALIDATED_LIVE_PROMOTION.md'):
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
    path = ROOT / 'docs' / 'RELEASE_CHECKLIST.md'
    text = path.read_text(encoding='utf-8') if path.exists() else ''
    if not path.exists():
        return ['docs/RELEASE_CHECKLIST.md is missing']
    if 'servo-cartesian endpoint is explicitly disabled until dispatcher/transport closure' in text:
        issues.append('release checklist still describes servo-cartesian as disabled')
    if 'servo-cartesian endpoint is wired through gateway validation, dispatcher mapping, and transport feedback closure' not in text:
        issues.append('release checklist missing servo-cartesian closure gate')
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
    if 'validate_servo_command' not in server or 'await CTX.ros.servo_cartesian' not in server:
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


def audit_generated_contract_artifacts() -> list[str]:
    issues = []
    generated = [
        ROOT / 'docs' / 'generated' / 'runtime_contract_manifest.json',
        ROOT / 'docs' / 'generated' / 'runtime_contract_summary.md',
    ]
    for path in generated:
        if not path.exists():
            issues.append(f'missing generated contract artifact: {path.relative_to(ROOT)}')
    contract_index = (ROOT / 'docs' / 'CONTRACT_INDEX.md').read_text(encoding='utf-8') if (ROOT / 'docs' / 'CONTRACT_INDEX.md').exists() else ''
    if 'generated/runtime_contract_summary.md' not in contract_index:
        issues.append('docs/CONTRACT_INDEX.md missing generated runtime contract summary reference')
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
    matrix = (ROOT / 'docs' / 'PACKAGE_SUPPORT_MATRIX.md').read_text(encoding='utf-8') if (ROOT / 'docs' / 'PACKAGE_SUPPORT_MATRIX.md').exists() else ''
    architecture = (ROOT / 'docs' / 'ARCHITECTURE_ALIGNMENT.md').read_text(encoding='utf-8') if (ROOT / 'docs' / 'ARCHITECTURE_ALIGNMENT.md').exists() else ''
    if '`arm_esp32_gateway` | runtime-core | yes' not in matrix:
        issues.append('docs/PACKAGE_SUPPORT_MATRIX.md must classify arm_esp32_gateway as runtime-core and active-lane included')
    if 'Runtime Core:' not in architecture or 'arm_esp32_gateway' not in architecture:
        issues.append('docs/ARCHITECTURE_ALIGNMENT.md must classify arm_esp32_gateway inside Runtime Core')
    if 'Experimental: `arm_hmi`' not in architecture:
        issues.append('docs/ARCHITECTURE_ALIGNMENT.md must leave only arm_hmi in the Experimental bucket')
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
    release_text = release_model.read_text(encoding='utf-8') if release_model.exists() else ''
    verify_text = verify_repo.read_text(encoding='utf-8') if verify_repo.exists() else ''
    if 'verification_summary.json' not in release_text:
        issues.append('release_state_model.py must derive repoGate from verification_summary.json')
    if '_write_verification_summary' not in verify_text:
        issues.append('verify_repository.py must emit verification_summary.json')
    if "'overallStatus': overall_status" not in verify_text:
        issues.append('verification summary must record overallStatus')
    if "'requiredSteps': required_steps" not in verify_text:
        issues.append('verification summary must record requiredSteps')
    if "'stepStatuses': step_statuses" not in verify_text:
        issues.append('verification summary must record stepStatuses')
    return issues


def audit_runtime_entrypoint_hardening() -> list[str]:
    issues = []
    launch_factory = ROOT / 'backend' / 'embodied_arm_ws' / 'src' / 'arm_bringup' / 'arm_bringup' / 'launch_factory.py'
    retired_wrapper = ROOT / 'backend' / 'embodied_arm_ws' / 'src' / 'arm_bringup' / 'launch' / 'runtime_real_authoritative.launch.py'
    migration_doc = ROOT / 'docs' / 'CONTROL_LANE_MIGRATION.md'
    text = launch_factory.read_text(encoding='utf-8') if launch_factory.exists() else ''
    wrapper_text = retired_wrapper.read_text(encoding='utf-8') if retired_wrapper.exists() else ''
    migration_text = migration_doc.read_text(encoding='utf-8') if migration_doc.exists() else ''
    if "build_runtime_launch_description('live_control')" in wrapper_text:
        issues.append('runtime_real_authoritative wrapper still bypasses legacy-alias retirement by launching live_control directly')
    if "build_runtime_launch_description('real_authoritative')" not in wrapper_text:
        issues.append('runtime_real_authoritative wrapper must resolve through the retired alias name so opt-in gating stays active')
    if 'EMBODIED_ARM_ALLOW_LEGACY_LIVE_ALIASES=true' not in wrapper_text:
        issues.append('runtime_real_authoritative wrapper must document the temporary migration environment opt-in')
    if 'requires `EMBODIED_ARM_ALLOW_LEGACY_LIVE_ALIASES=true`' not in migration_text:
        issues.append('CONTROL_LANE_MIGRATION.md must describe the retired wrapper opt-in requirement')
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

def main() -> int:
    clean_hygiene_residue()
    checks = [
        ('arm_msgs import leak', audit_arm_msgs_imports),
        ('raw /arm literal leak', audit_raw_arm_literals),
        ('self-referential fallback', audit_self_referential_fallbacks),
        ('actionized runtime contracts', audit_actionized_runtime_contracts),
        ('planner executor runtime contracts', audit_planner_executor_runtime_contracts),
        ('active profile consistency', audit_active_profile_consistency),
        ('runtime authority consistency', audit_runtime_authority_consistency),
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
        ('generated contract artifacts', audit_generated_contract_artifacts),
        ('runtime execution contracts', audit_runtime_execution_contracts),
        ('ros validation assets', audit_ros_validation_assets),
        ('runtime api contract alignment', audit_runtime_api_contract_alignment),
        ('repository gate evidence', audit_repository_gate_evidence),
        ('runtime entrypoint hardening', audit_runtime_entrypoint_hardening),
        ('active overlay isolation', audit_active_overlay_isolation),
        ('runtime truth fail fast', audit_runtime_truth_fail_fast),
        ('frontend lockfile registry', audit_frontend_lockfile_registry),
        ('validated live evidence', audit_validated_live_evidence),
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
