from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / 'src'

REQUIRED_PACKAGES = {
    'arm_description': ['urdf/arm.urdf.xacro', 'config/joint_limits.yaml', 'rviz/arm_default.rviz'],
    'arm_moveit_config': ['config/arm.srdf', 'config/ompl_planning.yaml', 'launch/demo.launch.py'],
    'arm_stm32_driver': ['include/arm_stm32_driver/protocol_codec.hpp', 'src/frame_parser.cpp'],
    'arm_esp32_gateway': ['arm_esp32_gateway/esp32_gateway_node.py', 'arm_esp32_gateway/board_health_parser.py'],
}

REQUIRED_INTERFACES = [
    'arm_interfaces/msg/Target.msg',
    'arm_interfaces/msg/TargetArray.msg',
    'arm_interfaces/msg/EventLog.msg',
    'arm_interfaces/msg/GraspCandidate.msg',
    'arm_interfaces/srv/Stop.srv',
    'arm_interfaces/srv/CaptureCalibrationFrame.srv',
    'arm_interfaces/action/Homing.action',
    'arm_interfaces/action/Recover.action',
]


def test_required_blueprint_packages_exist():
    for package, rels in REQUIRED_PACKAGES.items():
        package_root = ROOT / package
        assert package_root.exists(), f'{package} missing'
        for rel in rels:
            assert (package_root / rel).exists(), f'{package}/{rel} missing'


def test_required_blueprint_interfaces_exist():
    for rel in REQUIRED_INTERFACES:
        assert (ROOT / rel).exists(), f'{rel} missing'
