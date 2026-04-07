from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / 'backend' / 'embodied_arm_ws' / 'src'


def test_facade_packages_expose_core_and_node_adapter_layout():
    expected = {
        'arm_camera_driver': ['core', 'node_adapter'],
        'arm_perception': ['core', 'node_adapter'],
        'arm_scene_manager': ['core', 'node_adapter'],
        'arm_grasp_planner': ['core', 'node_adapter'],
    }
    for package, subdirs in expected.items():
        package_root = SRC / package / package
        for subdir in subdirs:
            init_py = package_root / subdir / '__init__.py'
            assert init_py.exists(), f'missing {package}.{subdir} package'


def test_runtime_supervisor_entrypoint_and_launch_registration_exist():
    setup_py = (SRC / 'arm_lifecycle_manager' / 'setup.py').read_text(encoding='utf-8')
    launch_factory = (SRC / 'arm_bringup' / 'arm_bringup' / 'launch_factory.py').read_text(encoding='utf-8')
    assert 'runtime_supervisor_node = arm_lifecycle_manager.runtime_supervisor_node:main' in setup_py
    assert "'enable_lifecycle_supervisor'" in launch_factory
    assert "Node(package='arm_lifecycle_manager', executable='runtime_supervisor_node'" in launch_factory
    assert "managed_lifecycle_manager_node = arm_lifecycle_manager.managed_lifecycle_manager_node:main" in setup_py
