from __future__ import annotations

import ast
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
SRC = ROOT / 'backend' / 'embodied_arm_ws' / 'src'
DEPRECATED = {'arm_msgs', 'arm_task_manager', 'arm_motion_bridge', 'arm_vision', 'arm_hmi'}
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
    SRC / 'arm_task_orchestrator' / 'arm_task_orchestrator' / 'task_orchestrator_node.py',
    ROOT / 'gateway' / 'ros_contract.py',
}


def _active_python_files() -> list[Path]:
    files = []
    for path in SRC.rglob('*.py'):
        if any(part in DEPRECATED for part in path.parts):
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
        if any(part in DEPRECATED for part in path.parts):
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
    text = path.read_text(encoding='utf-8') if path.exists() else ''
    required = [
        'arm_interfaces contract tests',
        'orchestrator state machine tests',
        'safety fault latch / stop policy tests',
        'launch smoke test',
        'sim pick-place test',
        'cancel task test',
        'reset fault and recover test',
    ]
    if not path.exists():
        issues.append('docs/P0_P1_TRACEABILITY.md is missing')
        return issues
    for item in required:
        if item not in text:
            issues.append(f'traceability doc missing item: {item}')
    return issues



def audit_runtime_launch_split() -> list[str]:
    issues = []
    official = SRC / 'arm_bringup' / 'launch' / 'official_runtime.launch.py'
    sim = SRC / 'arm_bringup' / 'launch' / 'runtime_sim.launch.py'
    real = SRC / 'arm_bringup' / 'launch' / 'runtime_real.launch.py'
    hybrid = SRC / 'arm_bringup' / 'launch' / 'runtime_hybrid.launch.py'
    full_demo = SRC / 'arm_bringup' / 'launch' / 'full_demo.launch.py'
    for path in (official, sim, real, hybrid):
        if not path.exists():
            issues.append(f'missing runtime launch file: {path.relative_to(ROOT)}')
    if issues:
        return issues
    official_text = official.read_text(encoding='utf-8')
    if 'Compatibility alias' not in official_text or 'runtime_sim.launch.py' not in official_text:
        issues.append('official_runtime.launch.py must be documented as a compatibility alias to runtime_sim.launch.py')
    factory = (SRC / 'arm_bringup' / 'arm_bringup' / 'launch_factory.py').read_text(encoding='utf-8')
    if 'RUNTIME_LANE_ALIASES' not in factory or "'official_runtime': 'sim'" not in factory:
        issues.append('launch_factory.py missing official_runtime -> sim alias mapping')
    demo_text = full_demo.read_text(encoding='utf-8') if full_demo.exists() else ''
    if full_demo.exists() and 'full_demo' not in demo_text:
        issues.append('full_demo launch should remain the demo entrypoint')
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
    if 'official_runtime.launch.py' not in backend_ws_readme or 'compatibility alias to the sim lane' not in backend_ws_readme:
        issues.append('backend workspace README must describe official_runtime.launch.py as a compatibility alias to the sim lane')
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


def main() -> int:
    checks = [
        ('arm_msgs import leak', audit_arm_msgs_imports),
        ('raw /arm literal leak', audit_raw_arm_literals),
        ('self-referential fallback', audit_self_referential_fallbacks),
        ('actionized runtime contracts', audit_actionized_runtime_contracts),
        ('planner executor runtime contracts', audit_planner_executor_runtime_contracts),
        ('active profile consistency', audit_active_profile_consistency),
        ('runtime launch split', audit_runtime_launch_split),
        ('release checklist alignment', audit_release_checklist_alignment),
        ('servo contract closure', audit_servo_contract_closure),
        ('calibration activation callback', audit_calibration_activation_callback),
        ('active package deps', audit_active_package_dependencies),
        ('readme alignment', audit_readme_alignment),
        ('environment matrix', audit_environment_matrix),
        ('p0 p1 traceability', audit_p0_p1_traceability),
        ('generated contract artifacts', audit_generated_contract_artifacts),
        ('ros validation assets', audit_ros_validation_assets),
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
