from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
LAUNCH_FACTORY = ROOT / 'backend' / 'embodied_arm_ws' / 'src' / 'arm_bringup' / 'arm_bringup' / 'launch_factory.py'


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
    spec = importlib.util.spec_from_file_location('runtime_lane_launch_factory_truthfulness', LAUNCH_FACTORY)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module



def test_preview_runtime_lane_manifest_defaults_to_non_authoritative_contract_only_planning() -> None:
    module = _load_launch_factory_module()
    manifest = module.runtime_lane_manifest()
    preview_lanes = {name: lane for name, lane in manifest.items() if name.endswith('_preview')}
    assert preview_lanes
    for lane_name, lane in preview_lanes.items():
        assert lane['enable_moveit'] is False, lane_name
        assert lane['planning_capability'] == 'contract_only', lane_name
        assert lane['planning_authoritative'] is False, lane_name
        assert lane['planning_backend_name'] == 'fallback_contract', lane_name



def test_preview_runtime_lane_manifest_preserves_reserved_esp32_stream_semantics() -> None:
    module = _load_launch_factory_module()
    manifest = module.runtime_lane_manifest()
    preview_lanes = {name: lane for name, lane in manifest.items() if name.endswith('_preview')}
    assert preview_lanes
    for lane_name, lane in preview_lanes.items():
        assert lane['esp32_stream_semantic'] == 'reserved', lane_name
        assert lane['esp32_frame_ingress_live'] is False, lane_name
        assert lane['frame_ingress_mode'] == 'reserved_endpoint', lane_name
        assert lane['forward_hardware_commands'] is False, lane_name
        assert lane['hardware_execution_mode'] == 'protocol_bridge', lane_name



def test_authoritative_simulation_lanes_publish_validated_planning_and_synthetic_frame_semantics() -> None:
    module = _load_launch_factory_module()
    manifest = module.runtime_lane_manifest()
    for lane_name in ('sim_authoritative', 'full_demo_authoritative'):
        lane = manifest[lane_name]
        assert lane['enable_moveit'] is False, lane_name
        assert lane['planning_capability'] == 'validated_sim', lane_name
        assert lane['planning_authoritative'] is True, lane_name
        assert lane['planning_backend_name'] == 'validated_sim_runtime', lane_name
        assert lane['scene_provider_mode'] == 'runtime_service', lane_name
        assert lane['grasp_provider_mode'] == 'runtime_service', lane_name
        assert lane['esp32_stream_semantic'] == 'synthetic_frame', lane_name
        assert lane['esp32_frame_ingress_live'] is True, lane_name
        assert lane['frame_ingress_mode'] == 'synthetic_frame_stream', lane_name
        assert lane['forward_hardware_commands'] is True, lane_name
        assert lane['hardware_execution_mode'] == 'authoritative_simulation', lane_name
        assert lane['stm32_authoritative_simulation'] is True, lane_name


def _launched_packages(module, mode: str) -> list[str]:
    launch_description = module.build_runtime_launch_description(mode)
    packages: list[str] = []
    for item in launch_description:
        kwargs = getattr(item, 'kwargs', None) or {}
        package = kwargs.get('package')
        if isinstance(package, str):
            packages.append(package)
    return packages


def test_preview_lanes_do_not_launch_runtime_service_provider_nodes() -> None:
    module = _load_launch_factory_module()
    packages = _launched_packages(module, 'sim_preview')
    assert 'arm_scene_manager' not in packages
    assert 'arm_grasp_planner' not in packages


def test_authoritative_lanes_launch_runtime_service_provider_nodes() -> None:
    module = _load_launch_factory_module()
    packages = _launched_packages(module, 'sim_authoritative')
    assert 'arm_scene_manager' in packages
    assert 'arm_grasp_planner' in packages
