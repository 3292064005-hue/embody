from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / 'src'


def test_task_orchestrator_exposes_action_server_contracts():
    text = (ROOT / 'arm_task_orchestrator' / 'arm_task_orchestrator' / 'task_orchestrator_node.py').read_text(encoding='utf-8')
    assert 'ActionServer' in text
    assert 'ActionNames.PICK_PLACE_TASK' in text
    assert 'ActionNames.HOMING' in text
    assert 'ActionNames.RECOVER' in text


def test_gateway_uses_action_client_for_long_running_tasks():
    text = (Path(__file__).resolve().parents[3] / 'gateway' / 'ros_bridge.py').read_text(encoding='utf-8')
    assert 'ActionClient' in text
    assert 'ActionNames.PICK_PLACE_TASK' in text
    assert 'ActionNames.HOMING' in text


def test_bringup_factory_can_include_moveit_launch():
    text = (ROOT / 'arm_bringup' / 'arm_bringup' / 'launch_factory.py').read_text(encoding='utf-8')
    assert 'arm_moveit_config' in text
    assert 'enable_moveit' in text
