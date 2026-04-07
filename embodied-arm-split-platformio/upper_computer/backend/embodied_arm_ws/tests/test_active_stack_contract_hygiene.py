from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / 'src'
DEPRECATED = {'arm_msgs', 'arm_task_manager', 'arm_motion_bridge', 'arm_vision', 'arm_hmi'}
ALLOW_ARM_MSGS = {
    SRC / 'arm_common' / 'arm_common' / 'interface_compat.py',
    ROOT / 'gateway' / 'ros_contract.py',
}
ALLOW_RAW_ARM = {
    SRC / 'arm_common' / 'arm_common' / 'topic_names.py',
    SRC / 'arm_common' / 'arm_common' / 'service_names.py',
    SRC / 'arm_common' / 'arm_common' / 'action_names.py',
    SRC / 'arm_motion_executor' / 'arm_motion_executor' / 'motion_executor_node.py',
    SRC / 'arm_motion_planner' / 'arm_motion_planner' / 'motion_planner_node.py',
    SRC / 'arm_scene_manager' / 'arm_scene_manager' / 'scene_manager_node.py',
    SRC / 'arm_grasp_planner' / 'arm_grasp_planner' / 'grasp_planner_node.py',
    SRC / 'arm_readiness_manager' / 'arm_readiness_manager' / 'readiness_manager_node.py',
    SRC / 'arm_task_orchestrator' / 'arm_task_orchestrator' / 'task_orchestrator_node.py',
}




def active_package_manifests():
    files = []
    for path in SRC.glob('*/package.xml'):
        if any(part in DEPRECATED for part in path.parts):
            continue
        files.append(path)
    return files

def active_files():
    files = []
    for path in SRC.rglob('*.py'):
        if any(part in DEPRECATED for part in path.parts):
            continue
        files.append(path)
    return files


def test_active_stack_does_not_import_arm_msgs_directly():
    for path in active_files():
        if path in ALLOW_ARM_MSGS:
            continue
        text = path.read_text(encoding='utf-8')
        assert 'arm_msgs' not in text, f'active stack should not reference arm_msgs directly: {path}'


def test_active_stack_avoids_raw_arm_contract_literals():
    for path in active_files():
        if path in ALLOW_RAW_ARM:
            continue
        text = path.read_text(encoding='utf-8')
        assert '/arm/' not in text, f'active stack should use TopicNames/ServiceNames constants: {path}'


def test_no_self_referential_topic_or_service_fallbacks():
    for path in active_files():
        text = path.read_text(encoding='utf-8')
        assert '= TopicNames.' not in text, f'self-referential TopicNames fallback in {path}'
        assert '= ServiceNames.' not in text, f'self-referential ServiceNames fallback in {path}'


def test_active_packages_do_not_depend_on_legacy_interface_or_vision_packages():
    for path in active_package_manifests():
        text = path.read_text(encoding='utf-8')
        assert '<depend>arm_msgs</depend>' not in text, f'active package should not depend on arm_msgs: {path}'
        assert '<depend>arm_vision</depend>' not in text, f'active package should not depend on arm_vision: {path}'
