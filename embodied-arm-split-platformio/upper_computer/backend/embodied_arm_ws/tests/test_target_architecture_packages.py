from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / 'src'
EXPECTED = {
    'arm_common': ['arm_common/error_codes.py', 'arm_common/topic_names.py'],
    'arm_interfaces': ['msg/TaskStatus.msg', 'srv/SetMode.srv', 'action/PickPlaceTask.action', 'msg/Target.msg'],
    'arm_description': ['urdf/arm.urdf.xacro', 'config/joint_limits.yaml'],
    'arm_moveit_config': ['config/arm.srdf', 'launch/demo.launch.py'],
    'arm_stm32_driver': ['include/arm_stm32_driver/protocol_codec.hpp', 'src/frame_parser.cpp'],
    'arm_esp32_gateway': ['arm_esp32_gateway/esp32_gateway_node.py'],
    'arm_camera_driver': ['arm_camera_driver/camera_node.py', 'arm_camera_driver/capture_backend.py'],
    'arm_perception': ['arm_perception/perception_node.py', 'arm_perception/target_tracker.py'],
    'arm_scene_manager': ['arm_scene_manager/scene_manager_node.py'],
    'arm_grasp_planner': ['arm_grasp_planner/grasp_planner_node.py'],
    'arm_hmi': ['arm_hmi/hmi_node.py'],
    'arm_sim': ['arm_sim/fake_hardware_node.py'],
    'arm_tools': ['arm_tools/verify_params.py'],
    'arm_tests': ['arm_tests/__init__.py'],
}


def test_target_architecture_packages_exist_with_key_files():
    for package, rel_paths in EXPECTED.items():
        package_root = ROOT / package
        assert package_root.exists(), f'{package} missing'
        for rel in rel_paths:
            assert (package_root / rel).exists(), f'{package}/{rel} missing'
