from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
LAUNCH_FACTORY = ROOT / 'backend' / 'embodied_arm_ws' / 'src' / 'arm_bringup' / 'arm_bringup' / 'launch_factory.py'
OFFICIAL = ROOT / 'backend' / 'embodied_arm_ws' / 'src' / 'arm_bringup' / 'launch' / 'official_runtime.launch.py'


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
    spec = importlib.util.spec_from_file_location('runtime_lane_launch_factory', LAUNCH_FACTORY)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_official_runtime_alias_maps_to_sim_lane() -> None:
    module = _load_launch_factory_module()
    assert module.normalize_runtime_lane('official_runtime') == 'sim'
    assert module.get_runtime_lane_spec('official_runtime').name == 'sim'


def test_lane_specs_preserve_expected_camera_and_transport_modes() -> None:
    module = _load_launch_factory_module()
    assert module.get_runtime_lane_spec('sim').camera_source == 'mock'
    assert module.get_runtime_lane_spec('sim').esp32_mode == 'sim'
    assert module.get_runtime_lane_spec('real').camera_source == 'topic'
    assert module.get_runtime_lane_spec('hybrid').camera_source == 'topic'


def test_official_launch_file_is_documented_as_compatibility_alias() -> None:
    text = OFFICIAL.read_text(encoding='utf-8')
    assert 'Compatibility alias' in text
    assert 'runtime_sim.launch.py' in text
