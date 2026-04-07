from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / 'src'


def test_motion_planner_node_exposes_runtime_inputs_and_action_server():
    text = (ROOT / 'arm_motion_planner' / 'arm_motion_planner' / 'motion_planner_node.py').read_text(encoding='utf-8')
    assert 'ActionServer' in text
    assert 'ActionNames.MANUAL_SERVO' in text
    assert 'TopicNames.INTERNAL_PLAN_TO_POSE' in text
    assert 'TopicNames.INTERNAL_PLAN_TO_JOINTS' in text


def test_motion_executor_node_exposes_runtime_inputs_and_action_server():
    text = (ROOT / 'arm_motion_executor' / 'arm_motion_executor' / 'motion_executor_node.py').read_text(encoding='utf-8')
    assert 'ActionServer' in text
    assert 'ActionNames.HOME_SEQUENCE' in text
    assert 'TopicNames.INTERNAL_EXECUTE_PLAN' in text
    assert 'TopicNames.INTERNAL_HARDWARE_CMD' in text


def test_bringup_factory_includes_description_and_moveit_launches():
    text = (ROOT / 'arm_bringup' / 'arm_bringup' / 'launch_factory.py').read_text(encoding='utf-8')
    assert 'arm_description' in text
    assert 'description.launch.py' in text
    assert 'arm_moveit_config' in text
