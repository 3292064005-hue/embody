from pathlib import Path
import importlib.util
import sys
import types

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / 'backend' / 'embodied_arm_ws' / 'src'
LAUNCH_FACTORY = SRC / 'arm_bringup' / 'arm_bringup' / 'launch_factory.py'


def _install_launch_stubs() -> None:
    if 'launch' in sys.modules:
        return
    launch = types.ModuleType('launch')
    actions = types.ModuleType('launch.actions')
    sources = types.ModuleType('launch.launch_description_sources')
    conditions = types.ModuleType('launch.conditions')
    substitutions = types.ModuleType('launch.substitutions')
    launch_ros = types.ModuleType('launch_ros')
    ros_actions = types.ModuleType('launch_ros.actions')
    ros_substitutions = types.ModuleType('launch_ros.substitutions')

    class LaunchDescription(list):
        pass

    class _Record:
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs

    launch.LaunchDescription = LaunchDescription
    actions.DeclareLaunchArgument = _Record
    actions.IncludeLaunchDescription = _Record
    sources.PythonLaunchDescriptionSource = _Record
    conditions.IfCondition = _Record
    substitutions.LaunchConfiguration = lambda name: f'cfg:{name}'
    substitutions.PathJoinSubstitution = lambda parts: '/'.join(str(item) for item in parts)
    substitutions.PythonExpression = lambda parts: ''.join(str(item) for item in parts)
    ros_actions.Node = _Record
    ros_actions.LifecycleNode = _Record
    ros_substitutions.FindPackageShare = lambda pkg: f'/opt/{pkg}'

    sys.modules['launch'] = launch
    sys.modules['launch.actions'] = actions
    sys.modules['launch.launch_description_sources'] = sources
    sys.modules['launch.conditions'] = conditions
    sys.modules['launch.substitutions'] = substitutions
    sys.modules['launch_ros'] = launch_ros
    sys.modules['launch_ros.actions'] = ros_actions
    sys.modules['launch_ros.substitutions'] = ros_substitutions


def _load_launch_factory_module():
    _install_launch_stubs()
    spec = importlib.util.spec_from_file_location('runtime_supervisor_launch_factory', LAUNCH_FACTORY)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


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
    module = _load_launch_factory_module()
    desc = module.build_runtime_launch_description('sim_preview')
    packages = [getattr(item, 'kwargs', {}).get('package') for item in desc if getattr(item, 'kwargs', {}).get('package')]
    executables = [getattr(item, 'kwargs', {}).get('executable') for item in desc if getattr(item, 'kwargs', {}).get('executable')]
    assert 'runtime_supervisor_node = arm_lifecycle_manager.runtime_supervisor_node:main' in setup_py
    assert 'managed_lifecycle_manager_node = arm_lifecycle_manager.managed_lifecycle_manager_node:main' in setup_py
    assert 'arm_lifecycle_manager' in packages
    assert 'runtime_supervisor_node' in executables
    assert 'managed_lifecycle_manager_node' in executables
