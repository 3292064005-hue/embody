from dataclasses import dataclass
from pathlib import Path

try:
    import yaml
except Exception:  # pragma: no cover
    yaml = None

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.conditions import IfCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution, PythonExpression
from launch_ros.actions import LifecycleNode, Node
from launch_ros.substitutions import FindPackageShare

RUNTIME_CORE_PACKAGES = (
    'arm_profiles',
    'arm_calibration',
    'arm_hardware_bridge',
    'arm_readiness_manager',
    'arm_safety_supervisor',
    'arm_camera_driver',
    'arm_perception',
    'arm_scene_manager',
    'arm_grasp_planner',
    'arm_motion_planner',
    'arm_motion_executor',
    'arm_task_orchestrator',
    'arm_diagnostics',
    'arm_logger',
)
RUNTIME_SUPERVISION_PACKAGES = ('arm_lifecycle_manager',)
COMPATIBILITY_PACKAGES = ('arm_task_manager', 'arm_motion_bridge')
EXPERIMENTAL_PACKAGES = ('arm_hmi', 'arm_esp32_gateway')
RUNTIME_LANE_ALIASES = {'official_runtime': 'sim'}


@dataclass(frozen=True)
class RuntimeLaneSpec:
    """Normalized runtime-lane description.

    Attributes:
        name: Canonical runtime lane name.
        simulate_hardware: Whether STM32 transport should run in simulation mode.
        camera_source: Runtime camera source override for the lane.
        esp32_mode: ESP32 transport mode for the lane.
        include_mock_targets: Whether legacy mock-target publisher should be injected.
        enable_moveit: Whether MoveIt demo stack is enabled by default.
        enable_rviz: Whether RViz is enabled by default.
        enable_lifecycle_supervisor: Whether lifecycle supervision is enabled by default.
        enable_managed_lifecycle: Whether managed lifecycle nodes are enabled by default.
        autostart_managed_lifecycle: Whether managed lifecycle nodes autostart by default.
        allow_simulation_fallback: Whether hardware bridge may degrade to simulation by default.
    """

    name: str
    simulate_hardware: bool
    camera_source: str
    esp32_mode: str
    include_mock_targets: bool = False
    enable_moveit: bool = True
    enable_rviz: bool = False
    enable_lifecycle_supervisor: bool = True
    enable_managed_lifecycle: bool = True
    autostart_managed_lifecycle: bool = True
    allow_simulation_fallback: bool = False


RUNTIME_LANE_SPECS = {
    'sim': RuntimeLaneSpec(name='sim', simulate_hardware=True, camera_source='mock', esp32_mode='sim'),
    'real': RuntimeLaneSpec(name='real', simulate_hardware=False, camera_source='topic', esp32_mode='wifi'),
    'hybrid': RuntimeLaneSpec(name='hybrid', simulate_hardware=True, camera_source='topic', esp32_mode='wifi'),
    'hw': RuntimeLaneSpec(name='hw', simulate_hardware=False, camera_source='mock', esp32_mode='wifi'),
    'full_demo': RuntimeLaneSpec(name='full_demo', simulate_hardware=True, camera_source='mock', esp32_mode='wifi', enable_rviz=True),
}
RUNTIME_PROFILE_PATH = Path(__file__).resolve().parents[1] / 'config' / 'runtime_profiles.yaml'


def _load_runtime_lane_specs() -> dict[str, RuntimeLaneSpec]:
    if yaml is None or not RUNTIME_PROFILE_PATH.exists():
        return dict(RUNTIME_LANE_SPECS)
    try:
        raw = yaml.safe_load(RUNTIME_PROFILE_PATH.read_text(encoding='utf-8')) or {}
    except Exception:
        return dict(RUNTIME_LANE_SPECS)
    specs: dict[str, RuntimeLaneSpec] = {}
    for name, payload in raw.items():
        if not isinstance(payload, dict):
            continue
        specs[str(name)] = RuntimeLaneSpec(
            name=str(name),
            simulate_hardware=bool(payload.get('simulate_hardware', False)),
            camera_source=str(payload.get('camera_source', 'mock')),
            esp32_mode=str(payload.get('esp32_mode', 'sim')),
            include_mock_targets=bool(payload.get('include_mock_targets', False)),
            enable_moveit=bool(payload.get('enable_moveit', True)),
            enable_rviz=bool(payload.get('enable_rviz', False)),
            enable_lifecycle_supervisor=bool(payload.get('enable_lifecycle_supervisor', True)),
            enable_managed_lifecycle=bool(payload.get('enable_managed_lifecycle', True)),
            autostart_managed_lifecycle=bool(payload.get('autostart_managed_lifecycle', True)),
            allow_simulation_fallback=bool(payload.get('allow_simulation_fallback', False)),
        )
    return specs or dict(RUNTIME_LANE_SPECS)


def normalize_runtime_lane(mode: str | None) -> str:
    """Normalize a launch lane or alias to a canonical runtime lane.

    Args:
        mode: Optional requested lane name.

    Returns:
        Canonical runtime lane name. Unknown lanes fall back to `sim`.
    """
    normalized = (mode or 'sim').strip().lower()
    normalized = RUNTIME_LANE_ALIASES.get(normalized, normalized)
    lane_specs = _load_runtime_lane_specs()
    return normalized if normalized in lane_specs else 'sim'


def get_runtime_lane_spec(mode: str | None, *, include_mock_targets: bool = False) -> RuntimeLaneSpec:
    """Return the canonical runtime-lane specification.

    Args:
        mode: Requested lane or alias.
        include_mock_targets: Force mock-target publisher injection for the returned lane.

    Returns:
        RuntimeLaneSpec: The canonical launch configuration for the lane.
    """
    lane_specs = _load_runtime_lane_specs()
    base = lane_specs[normalize_runtime_lane(mode)]
    return RuntimeLaneSpec(
        name=base.name,
        simulate_hardware=base.simulate_hardware,
        camera_source=base.camera_source,
        esp32_mode=base.esp32_mode,
        include_mock_targets=include_mock_targets or base.include_mock_targets,
        enable_moveit=base.enable_moveit,
        enable_rviz=base.enable_rviz,
        enable_lifecycle_supervisor=base.enable_lifecycle_supervisor,
        enable_managed_lifecycle=base.enable_managed_lifecycle,
        autostart_managed_lifecycle=base.autostart_managed_lifecycle,
        allow_simulation_fallback=base.allow_simulation_fallback,
    )


def _common_arguments(lane: RuntimeLaneSpec) -> tuple[list, dict[str, LaunchConfiguration]]:
    """Return launch-argument declarations and named substitutions."""
    package_share = FindPackageShare('arm_bringup')
    defaults = {
        'calibration': PathJoinSubstitution([package_share, 'config', 'default_calibration.yaml']),
        'task_profile': PathJoinSubstitution([package_share, 'config', 'task_pick_by_color.yaml']),
        'placement_profile': PathJoinSubstitution([package_share, 'config', 'placement_profiles.yaml']),
        'log_dir': 'logs',
        'stm32_port': '/dev/ttyUSB0',
        'camera_source': 'auto',
        'esp32_stream_endpoint': 'http://esp32.local/stream',
        'enable_moveit': 'true' if lane.enable_moveit else 'false',
        'enable_rviz': 'true' if lane.enable_rviz else 'false',
        'enable_lifecycle_supervisor': 'true' if lane.enable_lifecycle_supervisor else 'false',
        'enable_managed_lifecycle': 'true' if lane.enable_managed_lifecycle else 'false',
        'autostart_managed_lifecycle': 'true' if lane.autostart_managed_lifecycle else 'false',
        'allow_simulation_fallback': 'true' if lane.allow_simulation_fallback else 'false',
    }
    declarations = [DeclareLaunchArgument(name, default_value=value) for name, value in defaults.items()]
    return declarations, {name: LaunchConfiguration(name) for name in defaults}


def _managed_node(*, package: str, executable: str, name: str, parameters: list | None = None, condition=None):
    return LifecycleNode(package=package, executable=executable, name=name, parameters=parameters or [], output='screen', condition=condition)


def _regular_node(*, package: str, executable: str, name: str, parameters: list | None = None, condition=None):
    return Node(package=package, executable=executable, name=name, parameters=parameters or [], output='screen', condition=condition)


def _node_actions(*, enable_managed_lifecycle, package: str, executable: str, name: str, parameters: list | None = None):
    managed_condition = IfCondition(enable_managed_lifecycle)
    regular_condition = IfCondition(PythonExpression(['not ', enable_managed_lifecycle]))
    return [
        _managed_node(package=package, executable=executable, name=name, parameters=parameters, condition=managed_condition),
        _regular_node(package=package, executable=executable, name=name, parameters=parameters, condition=regular_condition),
    ]


def _supervision_nodes(*, enable_lifecycle_supervisor, enable_managed_lifecycle, autostart_managed_lifecycle) -> list:
    """Return lifecycle supervision nodes used by the active runtime lanes."""
    return [
        Node(package='arm_lifecycle_manager', executable='managed_lifecycle_manager_node', name='managed_lifecycle_manager_node', parameters=[{'autostart': autostart_managed_lifecycle}], condition=IfCondition(enable_managed_lifecycle), output='screen'),
        Node(package='arm_lifecycle_manager', executable='runtime_supervisor_node', name='runtime_supervisor_node', condition=IfCondition(enable_lifecycle_supervisor), output='screen'),
    ]


def _runtime_core_nodes(*, configs: dict[str, LaunchConfiguration], lane: RuntimeLaneSpec) -> list:
    """Build runtime-core node actions for a canonical lane specification."""
    task_profile = configs['task_profile']
    placement_profile = configs['placement_profile']
    calibration = configs['calibration']
    log_dir = configs['log_dir']
    stm32_port = configs['stm32_port']
    esp32_stream = configs['esp32_stream_endpoint']
    enable_moveit = configs['enable_moveit']
    enable_rviz = configs['enable_rviz']
    enable_lifecycle_supervisor = configs['enable_lifecycle_supervisor']
    enable_managed_lifecycle = configs['enable_managed_lifecycle']
    autostart_managed_lifecycle = configs['autostart_managed_lifecycle']
    allow_simulation_fallback = configs['allow_simulation_fallback']
    resolved_camera_source = PythonExpression([
        "'",
        lane.camera_source,
        "' if '",
        configs['camera_source'],
        "' == 'auto' else '",
        configs['camera_source'],
        "'",
    ])
    moveit_share = FindPackageShare('arm_moveit_config')
    description_share = FindPackageShare('arm_description')

    nodes: list = [
        IncludeLaunchDescription(
            PythonLaunchDescriptionSource(PathJoinSubstitution([description_share, 'launch', 'description.launch.py'])),
            launch_arguments={'publish_robot_description': 'true'}.items(),
        ),
        IncludeLaunchDescription(
            PythonLaunchDescriptionSource(PathJoinSubstitution([moveit_share, 'launch', 'demo.launch.py'])),
            condition=IfCondition(enable_moveit),
            launch_arguments={'enable_rviz': enable_rviz}.items(),
        ),
        *_node_actions(
            enable_managed_lifecycle=enable_managed_lifecycle,
            package='arm_profiles',
            executable='profile_manager_node',
            name='profile_manager_node',
            parameters=[{'task_profile_path': task_profile, 'placement_profile_path': placement_profile}],
        ),
        *_node_actions(enable_managed_lifecycle=enable_managed_lifecycle, package='arm_calibration', executable='calibration_manager_node', name='calibration_manager_node', parameters=[{'config_path': calibration}]),
        *_node_actions(enable_managed_lifecycle=enable_managed_lifecycle, package='arm_hardware_bridge', executable='stm32_serial_node', name='stm32_serial_node', parameters=[{'port': stm32_port if not lane.simulate_hardware else 'sim://stm32', 'baudrate': 115200, 'simulate_hardware': lane.simulate_hardware, 'allow_simulation_fallback': allow_simulation_fallback if not lane.simulate_hardware else 'false'}]),
        *_node_actions(enable_managed_lifecycle=enable_managed_lifecycle, package='arm_hardware_bridge', executable='esp32_link_node', name='esp32_link_node', parameters=[{'mode': lane.esp32_mode, 'stream_endpoint': esp32_stream if not lane.simulate_hardware else 'sim://camera'}]),
        *_node_actions(enable_managed_lifecycle=enable_managed_lifecycle, package='arm_hardware_bridge', executable='hardware_state_aggregator_node', name='hardware_state_aggregator_node'),
        *_node_actions(enable_managed_lifecycle=enable_managed_lifecycle, package='arm_hardware_bridge', executable='hardware_command_dispatcher_node', name='hardware_command_dispatcher'),
        *_node_actions(enable_managed_lifecycle=enable_managed_lifecycle, package='arm_readiness_manager', executable='readiness_manager_node', name='readiness_manager'),
        *_node_actions(enable_managed_lifecycle=enable_managed_lifecycle, package='arm_safety_supervisor', executable='safety_supervisor_node', name='safety_supervisor'),
        *_node_actions(enable_managed_lifecycle=enable_managed_lifecycle, package='arm_camera_driver', executable='camera_driver', name='camera_driver_node', parameters=[{'source_type': resolved_camera_source}]),
        *_node_actions(enable_managed_lifecycle=enable_managed_lifecycle, package='arm_perception', executable='perception_node', name='perception_node'),
        *_node_actions(enable_managed_lifecycle=enable_managed_lifecycle, package='arm_scene_manager', executable='scene_manager', name='scene_manager'),
        *_node_actions(enable_managed_lifecycle=enable_managed_lifecycle, package='arm_grasp_planner', executable='grasp_planner', name='grasp_planner'),
        *_node_actions(enable_managed_lifecycle=enable_managed_lifecycle, package='arm_motion_planner', executable='motion_planner_node', name='motion_planner_node'),
        *_node_actions(enable_managed_lifecycle=enable_managed_lifecycle, package='arm_motion_executor', executable='motion_executor_node', name='motion_executor_node'),
        *_node_actions(enable_managed_lifecycle=enable_managed_lifecycle, package='arm_task_orchestrator', executable='task_orchestrator_node', name='task_orchestrator', parameters=[{'task_profile_path': task_profile}]),
        *_node_actions(enable_managed_lifecycle=enable_managed_lifecycle, package='arm_diagnostics', executable='diagnostics_summary_node', name='diagnostics_summary'),
        *_node_actions(enable_managed_lifecycle=enable_managed_lifecycle, package='arm_logger', executable='event_logger_node', name='event_logger_node', parameters=[{'log_dir': log_dir}]),
        *_node_actions(enable_managed_lifecycle=enable_managed_lifecycle, package='arm_logger', executable='metrics_logger_node', name='metrics_logger_node', parameters=[{'log_dir': log_dir}]),
        *_supervision_nodes(
            enable_lifecycle_supervisor=enable_lifecycle_supervisor,
            enable_managed_lifecycle=enable_managed_lifecycle,
            autostart_managed_lifecycle=autostart_managed_lifecycle,
        ),
    ]
    if lane.include_mock_targets:
        nodes.append(Node(package='arm_mock_tools', executable='mock_target_publisher_node', name='legacy_mock_target_publisher'))
    return nodes


def _experimental_nodes() -> list:
    return []


def build_runtime_launch_description(mode: str = 'sim', *, include_mock_targets: bool = False) -> LaunchDescription:
    """Build a launch description for a canonical runtime lane or compatibility alias."""
    lane = get_runtime_lane_spec(mode, include_mock_targets=include_mock_targets)
    declarations, configs = _common_arguments(lane)
    nodes = _runtime_core_nodes(configs=configs, lane=lane)
    if lane.name == 'full_demo':
        nodes.extend(_experimental_nodes())
    return LaunchDescription([*declarations, *nodes])


def build_launch_description(mode: str = 'sim', *, include_mock_targets: bool = False) -> LaunchDescription:
    """Backward-compatible entrypoint for pre-split launch callers."""
    return build_runtime_launch_description(mode, include_mock_targets=include_mock_targets)


def build_official_runtime_launch_description(mode: str = 'sim', *, include_mock_targets: bool = False) -> LaunchDescription:
    """Compatibility wrapper for the historic official_runtime alias.

    Args:
        mode: Requested lane or alias. `official_runtime` maps to the canonical `sim` lane.
        include_mock_targets: Whether to force mock target injection.
    """
    return build_runtime_launch_description(mode, include_mock_targets=include_mock_targets)


def build_calibration_launch_description() -> LaunchDescription:
    return LaunchDescription(
        _node_actions(
            enable_managed_lifecycle='true',
            package='arm_calibration',
            executable='calibration_manager_node',
            name='calibration_manager_node',
        )
    )
