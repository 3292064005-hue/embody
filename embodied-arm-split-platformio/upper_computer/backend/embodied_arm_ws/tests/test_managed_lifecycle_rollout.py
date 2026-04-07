from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / 'backend' / 'embodied_arm_ws' / 'src'


def test_managed_lifecycle_manager_entrypoint_and_launch_registration_exist():
    setup_py = (SRC / 'arm_lifecycle_manager' / 'setup.py').read_text(encoding='utf-8')
    launch_factory = (SRC / 'arm_bringup' / 'arm_bringup' / 'launch_factory.py').read_text(encoding='utf-8')
    assert 'managed_lifecycle_manager_node = arm_lifecycle_manager.managed_lifecycle_manager_node:main' in setup_py
    assert "'enable_managed_lifecycle'" in launch_factory
    assert 'LifecycleNode' in launch_factory
    assert "executable='managed_lifecycle_manager_node'" in launch_factory


def test_official_runtime_nodes_import_managed_lifecycle_support():
    expected = {'arm_profiles/arm_profiles/profile_manager_node.py','arm_calibration/arm_calibration/calibration_manager_node.py','arm_hardware_bridge/arm_hardware_bridge/stm32_serial_node.py','arm_hardware_bridge/arm_hardware_bridge/esp32_link_node.py','arm_hardware_bridge/arm_hardware_bridge/hardware_state_aggregator_node.py','arm_hardware_bridge/arm_hardware_bridge/hardware_command_dispatcher_node.py','arm_readiness_manager/arm_readiness_manager/readiness_manager_node.py','arm_safety_supervisor/arm_safety_supervisor/safety_supervisor_node.py','arm_motion_planner/arm_motion_planner/motion_planner_node.py','arm_motion_executor/arm_motion_executor/motion_executor_node.py','arm_task_orchestrator/arm_task_orchestrator/task_orchestrator_node.py','arm_diagnostics/arm_diagnostics/diagnostics_summary_node.py','arm_logger/arm_logger/event_logger_node.py','arm_logger/arm_logger/metrics_logger_node.py','arm_scene_manager/arm_scene_manager/scene_manager_node.py','arm_grasp_planner/arm_grasp_planner/grasp_planner_node.py'}
    for rel in expected:
        text = (SRC / rel).read_text(encoding='utf-8')
        assert 'ManagedLifecycleNode' in text
        assert 'lifecycle_main' in text


def test_camera_and_perception_runtime_adapters_exist():
    camera_runtime = SRC / 'arm_camera_driver' / 'arm_camera_driver' / 'camera_runtime_node.py'
    perception_runtime = SRC / 'arm_perception' / 'arm_perception' / 'perception_runtime_node.py'
    assert camera_runtime.exists()
    assert perception_runtime.exists()
    assert 'CameraRuntimeNode' in camera_runtime.read_text(encoding='utf-8')
    assert 'PerceptionRuntimeNode' in perception_runtime.read_text(encoding='utf-8')
