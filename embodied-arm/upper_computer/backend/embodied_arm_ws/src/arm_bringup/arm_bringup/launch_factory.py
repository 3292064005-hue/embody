import os
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

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
    'arm_esp32_gateway',
    'arm_readiness_manager',
    'arm_safety_supervisor',
    'arm_camera_driver',
    'arm_perception',
    'arm_scene_manager',
    'arm_grasp_planner',
    'arm_motion_planner',
    'arm_motion_executor',
    'arm_task_orchestrator',
    'arm_bt_runtime',
    'arm_bt_nodes',
    'arm_diagnostics',
    'arm_logger',
)
RUNTIME_SUPERVISION_PACKAGES = ('arm_lifecycle_manager',)
COMPATIBILITY_PACKAGES = ('arm_task_manager', 'arm_motion_bridge', 'arm_vision')
EXPERIMENTAL_PACKAGES = ('arm_hmi',)
RUNTIME_LANE_ALIASES = {
    'official_runtime': 'sim_preview',
    'sim': 'sim_preview',
    'authoritative_runtime': 'sim_authoritative',
    'sim_validated': 'sim_authoritative',
    'sim_perception_realistic': 'sim_perception_preview',
    'real': 'real_preview',
    'hybrid': 'hybrid_preview',
    'hw': 'hw_preview',
    'full_demo': 'full_demo_preview',
    'full_demo_validated': 'full_demo_authoritative',
    'real_authoritative': 'real_candidate',
    'real_authoritative_live': 'real_validated_live',
    'real_validated': 'real_candidate',
    'validated_live': 'real_validated_live',
    'live': 'real_validated_live',
}


@dataclass(frozen=True)
class RuntimeLaneSpec:
    """Normalized runtime-lane description loaded from ``runtime_profiles.yaml``."""

    name: str
    simulate_hardware: bool
    camera_source: str
    esp32_mode: str
    include_mock_targets: bool = False
    mock_camera_profile: str = 'authoritative_demo'
    enable_esp32_gateway: bool = False
    esp32_base_url: str = 'http://esp32.local'
    enable_moveit: bool = False
    enable_rviz: bool = False
    enable_lifecycle_supervisor: bool = True
    enable_managed_lifecycle: bool = True
    autostart_managed_lifecycle: bool = True
    allow_simulation_fallback: bool = False
    planning_capability: str = 'contract_only'
    planning_authoritative: bool = False
    planning_backend_name: str = 'fallback_contract'
    planning_backend_profile: str = ''
    scene_provider_mode: str = 'embedded_core'
    grasp_provider_mode: str = 'embedded_core'
    esp32_stream_semantic: str = 'reserved'
    esp32_frame_ingress_live: bool = False
    frame_ingress_mode: str = 'reserved_endpoint'
    forward_hardware_commands: bool = False
    hardware_execution_mode: str = 'protocol_bridge'
    execution_backbone: str = 'protocol_bridge'
    execution_backbone_declared: bool = True
    stm32_authoritative_simulation: bool = False
    enable_ros2_control: bool = False
    planning_backend_declared: bool = True
    public_runtime_tier: str = ''
    task_workbench_visible: bool | None = None
    task_execution_interactive: bool | None = None


# Fail-safe fallback used only when runtime_profiles.yaml is unavailable or invalid.
# The canonical runtime authority lives in config/runtime_authority.yaml; runtime_profiles.yaml is the generated launch-time projection.
RUNTIME_LANE_SPECS = {
    'sim_preview': RuntimeLaneSpec(name='sim_preview', simulate_hardware=True, camera_source='mock', esp32_mode='sim'),
    'sim_perception_preview': RuntimeLaneSpec(name='sim_perception_preview', simulate_hardware=True, camera_source='mock', esp32_mode='sim', mock_camera_profile='realistic_empty'),
    'real_preview': RuntimeLaneSpec(name='real_preview', simulate_hardware=False, camera_source='topic', esp32_mode='wifi', enable_esp32_gateway=True),
    'hybrid_preview': RuntimeLaneSpec(name='hybrid_preview', simulate_hardware=True, camera_source='topic', esp32_mode='wifi', mock_camera_profile='realistic_empty', enable_esp32_gateway=True, allow_simulation_fallback=True),
    'hw_preview': RuntimeLaneSpec(name='hw_preview', simulate_hardware=False, camera_source='mock', esp32_mode='wifi', enable_esp32_gateway=True),
    'full_demo_preview': RuntimeLaneSpec(name='full_demo_preview', simulate_hardware=True, camera_source='mock', esp32_mode='wifi', enable_esp32_gateway=True, enable_rviz=True),
    'sim_authoritative': RuntimeLaneSpec(name='sim_authoritative', simulate_hardware=True, camera_source='mock', esp32_mode='sim', planning_capability='validated_sim', planning_authoritative=True, planning_backend_name='validated_sim_runtime', planning_backend_profile='validated_sim_default', scene_provider_mode='runtime_service', grasp_provider_mode='runtime_service', esp32_stream_semantic='synthetic_frame', esp32_frame_ingress_live=True, frame_ingress_mode='synthetic_frame_stream', forward_hardware_commands=True, hardware_execution_mode='authoritative_simulation', execution_backbone='dispatcher', execution_backbone_declared=True, enable_ros2_control=False, planning_backend_declared=True, public_runtime_tier='validated_sim', task_workbench_visible=True, task_execution_interactive=True, stm32_authoritative_simulation=True),
    'full_demo_authoritative': RuntimeLaneSpec(name='full_demo_authoritative', simulate_hardware=True, camera_source='mock', esp32_mode='wifi', enable_esp32_gateway=True, enable_rviz=True, planning_capability='validated_sim', planning_authoritative=True, planning_backend_name='validated_sim_runtime', planning_backend_profile='validated_sim_default', scene_provider_mode='runtime_service', grasp_provider_mode='runtime_service', esp32_stream_semantic='synthetic_frame', esp32_frame_ingress_live=True, frame_ingress_mode='synthetic_frame_stream', forward_hardware_commands=True, hardware_execution_mode='authoritative_simulation', execution_backbone='dispatcher', execution_backbone_declared=True, enable_ros2_control=False, planning_backend_declared=True, public_runtime_tier='validated_sim', task_workbench_visible=True, task_execution_interactive=True, stm32_authoritative_simulation=True),
    'real_candidate': RuntimeLaneSpec(name='real_candidate', simulate_hardware=False, camera_source='topic', esp32_mode='wifi', enable_esp32_gateway=True, planning_capability='validated_live', planning_authoritative=True, planning_backend_name='validated_live_bridge', planning_backend_profile='validated_live_bridge', scene_provider_mode='runtime_service', grasp_provider_mode='runtime_service', esp32_stream_semantic='live_frame_summary', esp32_frame_ingress_live=True, frame_ingress_mode='live_camera_stream', forward_hardware_commands=True, hardware_execution_mode='ros2_control_live', execution_backbone='ros2_control', execution_backbone_declared=False, enable_ros2_control=True, planning_backend_declared=False, public_runtime_tier='preview', task_workbench_visible=False, task_execution_interactive=False, stm32_authoritative_simulation=False),
    'real_validated_live': RuntimeLaneSpec(name='real_validated_live', simulate_hardware=False, camera_source='topic', esp32_mode='wifi', enable_esp32_gateway=True, planning_capability='validated_live', planning_authoritative=True, planning_backend_name='validated_live_bridge', planning_backend_profile='validated_live_bridge', scene_provider_mode='runtime_service', grasp_provider_mode='runtime_service', esp32_stream_semantic='live_frame_summary', esp32_frame_ingress_live=True, frame_ingress_mode='live_camera_stream', forward_hardware_commands=True, hardware_execution_mode='ros2_control_live', execution_backbone='ros2_control', execution_backbone_declared=False, enable_ros2_control=True, planning_backend_declared=False, public_runtime_tier='preview', task_workbench_visible=False, task_execution_interactive=False, stm32_authoritative_simulation=False),
}
RUNTIME_PROFILE_PATH = Path(__file__).resolve().parents[1] / 'config' / 'runtime_profiles.yaml'
PLANNING_BACKEND_PROFILE_PATH = Path(__file__).resolve().parents[1] / 'config' / 'planning_backend_profiles.yaml'
RUNTIME_PROMOTION_RECEIPT_PATH = Path(__file__).resolve().parents[1] / 'config' / 'runtime_promotion_receipts.yaml'
VALIDATED_LIVE_EVIDENCE_PATH = Path(__file__).resolve().parents[1] / 'config' / 'validated_live_evidence.yaml'
TARGET_RUNTIME_GATE_PATH = Path(__file__).resolve().parents[5] / 'artifacts' / 'release_gates' / 'target_runtime_gate.json'
UPPER_COMPUTER_ROOT = Path(__file__).resolve().parents[5]
_DEFAULT_BACKEND_DECLARATIONS = {'validated_sim_default': True, 'validated_live_bridge': False}
_DEFAULT_RUNTIME_PROMOTION_RECEIPTS = {'validated_sim': True, 'validated_live': False}


def _effective_runtime_profile_path() -> Path:
    env_path = os.environ.get('EMBODIED_ARM_RUNTIME_PROFILES_FILE', '').strip()
    return Path(env_path).expanduser() if env_path else RUNTIME_PROFILE_PATH


def _load_runtime_lane_specs() -> dict[str, RuntimeLaneSpec]:
    """Load runtime-lane specifications from the generated authority artifact.

    Args:
        None. The effective path is resolved from the environment override or the
        canonical generated runtime profile file.

    Returns:
        Mapping of lane name to ``RuntimeLaneSpec``.

    Raises:
        RuntimeError: The runtime-profile artifact is missing, YAML support is
            unavailable, parsing fails, or the payload is structurally invalid.

    Boundary behavior:
        Production and CI paths fail fast when the generated runtime-profile
        artifact is missing or malformed. The launch stack no longer silently
        falls back to baked-in lane maps because that would hide authority drift.
    """
    path = _effective_runtime_profile_path()
    if yaml is None or not path.exists():
        raise RuntimeError(f'runtime profiles file missing or yaml unavailable: {path}')
    try:
        raw = yaml.safe_load(path.read_text(encoding='utf-8')) or {}
    except Exception as exc:
        raise RuntimeError(f'failed to parse runtime profiles: {path}: {exc}') from exc
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
            mock_camera_profile=str(payload.get('mock_camera_profile', 'authoritative_demo')),
            enable_esp32_gateway=bool(payload.get('enable_esp32_gateway', False)),
            esp32_base_url=str(payload.get('esp32_base_url', 'http://esp32.local')),
            enable_moveit=bool(payload.get('enable_moveit', False)),
            enable_rviz=bool(payload.get('enable_rviz', False)),
            enable_lifecycle_supervisor=bool(payload.get('enable_lifecycle_supervisor', True)),
            enable_managed_lifecycle=bool(payload.get('enable_managed_lifecycle', True)),
            autostart_managed_lifecycle=bool(payload.get('autostart_managed_lifecycle', True)),
            allow_simulation_fallback=bool(payload.get('allow_simulation_fallback', False)),
            planning_capability=str(payload.get('planning_capability', 'contract_only')),
            planning_authoritative=bool(payload.get('planning_authoritative', False)),
            planning_backend_name=str(payload.get('planning_backend_name', 'fallback_contract')),
            planning_backend_profile=str(payload.get('planning_backend_profile', '')),
            scene_provider_mode=str(payload.get('scene_provider_mode', 'embedded_core')),
            grasp_provider_mode=str(payload.get('grasp_provider_mode', 'embedded_core')),
            esp32_stream_semantic=str(payload.get('esp32_stream_semantic', 'reserved')),
            esp32_frame_ingress_live=bool(payload.get('esp32_frame_ingress_live', False)),
            frame_ingress_mode=str(payload.get('frame_ingress_mode', 'reserved_endpoint')),
            forward_hardware_commands=bool(payload.get('forward_hardware_commands', False)),
            hardware_execution_mode=str(payload.get('hardware_execution_mode', 'protocol_bridge')),
            execution_backbone=str(payload.get('execution_backbone', 'protocol_bridge')),
            execution_backbone_declared=bool(payload.get('execution_backbone_declared', True)),
            stm32_authoritative_simulation=bool(payload.get('stm32_authoritative_simulation', False)),
            enable_ros2_control=bool(payload.get('enable_ros2_control', False)),
            planning_backend_declared=bool(payload.get('planning_backend_declared', True)),
            public_runtime_tier=str(payload.get('public_runtime_tier', '')),
            task_workbench_visible=None if payload.get('task_workbench_visible') is None else bool(payload.get('task_workbench_visible')),
            task_execution_interactive=None if payload.get('task_execution_interactive') is None else bool(payload.get('task_execution_interactive')),
        )
    if specs:
        return specs
    raise RuntimeError(f'runtime profiles must define at least one lane: {path}')




def _effective_runtime_promotion_receipt_path() -> Path:
    env_path = os.environ.get('EMBODIED_ARM_RUNTIME_PROMOTION_RECEIPTS_FILE', '').strip()
    return Path(env_path).expanduser() if env_path else RUNTIME_PROMOTION_RECEIPT_PATH

def _effective_validated_live_evidence_path() -> Path:
    env_path = os.environ.get('EMBODIED_ARM_VALIDATED_LIVE_EVIDENCE_FILE', '').strip()
    return Path(env_path).expanduser() if env_path else VALIDATED_LIVE_EVIDENCE_PATH


def _effective_target_runtime_gate_path() -> Path:
    env_path = os.environ.get('EMBODIED_ARM_TARGET_RUNTIME_GATE_FILE', '').strip()
    return Path(env_path).expanduser() if env_path else TARGET_RUNTIME_GATE_PATH


def _load_target_runtime_gate_report() -> dict[str, Any]:
    path = _effective_target_runtime_gate_path()
    if not path.exists():
        return {}
    try:
        import json
        raw = json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        return {}
    return raw if isinstance(raw, dict) else {}


def _load_validated_live_evidence() -> dict[str, Any]:
    path = _effective_validated_live_evidence_path()
    if yaml is None or not path.exists():
        return {'schema_version': 1, 'evidence': {}}
    try:
        raw = yaml.safe_load(path.read_text(encoding='utf-8')) or {}
    except Exception:
        return {'schema_version': 1, 'evidence': {}}
    if not isinstance(raw, dict):
        return {'schema_version': 1, 'evidence': {}}
    evidence = raw.get('evidence', {})
    if not isinstance(evidence, dict):
        evidence = {}
    return {'schema_version': int(raw.get('schema_version', 1) or 1), 'evidence': evidence}


def _validated_live_artifact_passed(marker: str) -> bool:
    evidence_manifest = _load_validated_live_evidence()
    evidence = evidence_manifest.get('evidence', {}) if isinstance(evidence_manifest.get('evidence'), dict) else {}
    item = evidence.get(marker, {}) if isinstance(evidence.get(marker), dict) else {}
    if str(item.get('status', '') or '').strip().lower() != 'passed':
        return False
    artifact = str(item.get('artifact', '') or '').strip()
    if not artifact or not (UPPER_COMPUTER_ROOT / artifact).exists():
        return False
    gate_field = str(item.get('gate_field', '') or '').strip()
    if gate_field:
        report = _load_target_runtime_gate_report()
        if str(report.get(gate_field, '') or '').strip().lower() != 'passed':
            return False
    return True


def _validated_live_target_gate_passed() -> bool:
    evidence_manifest = _load_validated_live_evidence()
    evidence = evidence_manifest.get('evidence', {}) if isinstance(evidence_manifest.get('evidence'), dict) else {}
    item = evidence.get('target_runtime_gate_passed', {}) if isinstance(evidence.get('target_runtime_gate_passed'), dict) else {}
    if str(item.get('status', '') or '').strip().lower() != 'passed':
        return False
    artifact = str(item.get('artifact', '') or '').strip()
    if not artifact or not (UPPER_COMPUTER_ROOT / artifact).exists():
        return False
    report = _load_target_runtime_gate_report()
    return str(report.get('targetGate', '') or '').strip().lower() == 'passed' and not bool(report.get('hasBlockingStep', False))


def _receipt_has_marker(payload: dict[str, Any], marker: str) -> bool:
    return marker in {str(item).strip() for item in payload.get('evidence', []) if str(item).strip()}


def _validated_live_backbone_declared(spec: RuntimeLaneSpec, *, planning_backend_declared: bool) -> bool:
    return bool(
        planning_backend_declared
        and spec.execution_backbone_declared
        and spec.enable_ros2_control
        and spec.execution_backbone == 'ros2_control'
        and spec.hardware_execution_mode == 'ros2_control_live'
        and spec.frame_ingress_mode == 'live_camera_stream'
        and spec.scene_provider_mode == 'runtime_service'
        and spec.grasp_provider_mode == 'runtime_service'
        and spec.planning_authoritative
        and spec.forward_hardware_commands
        and spec.esp32_frame_ingress_live
    )


def _receipt_effective(payload: dict[str, Any] | None, *, spec: RuntimeLaneSpec, planning_backend_declared: bool) -> bool:
    data = payload if isinstance(payload, dict) else {}
    if not bool(data.get('promoted', False)):
        return False
    required_markers = ('receipt_id', 'checked_by', 'checked_at')
    if any(not str(data.get(marker, '') or '').strip() for marker in required_markers):
        return False
    required_evidence = [str(item).strip() for item in data.get('required_evidence', []) if str(item).strip()]
    for marker in required_evidence:
        if not _receipt_has_marker(data, marker):
            return False
        if marker == 'validated_live_backbone_declared' and not _validated_live_backbone_declared(spec, planning_backend_declared=planning_backend_declared):
            return False
        if marker == 'live_planning_backend_declared' and not planning_backend_declared:
            return False
        if marker == 'ros2_control_execution_backbone_declared' and not _validated_live_backbone_declared(spec, planning_backend_declared=planning_backend_declared):
            return False
        if marker == 'target_runtime_gate_passed' and not _validated_live_target_gate_passed():
            return False
        if marker in {'hil_gate_passed', 'hil_smoke_passed', 'release_checklist_signed'} and not _validated_live_artifact_passed(marker):
            return False
    return True


def _load_runtime_promotion_receipts(*, spec: RuntimeLaneSpec, planning_backend_declared: bool = False) -> dict[str, bool]:
    receipts = dict(_DEFAULT_RUNTIME_PROMOTION_RECEIPTS)
    path = _effective_runtime_promotion_receipt_path()
    if yaml is None or not path.exists():
        return receipts
    try:
        raw = yaml.safe_load(path.read_text(encoding='utf-8')) or {}
    except Exception:
        return receipts
    if not isinstance(raw, dict):
        return receipts
    for name, payload in raw.items():
        if isinstance(payload, dict):
            receipts[str(name)] = _receipt_effective(
                payload,
                spec=spec,
                planning_backend_declared=planning_backend_declared,
            )
    return receipts


def runtime_promotion_receipts(*, spec: RuntimeLaneSpec, planning_backend_declared: bool = False) -> dict[str, bool]:
    """Return effective runtime-promotion receipt status for each public tier.

    A receipt is effective only when its promotion bit is true and the required
    metadata/evidence markers are present. This keeps validated_live fail-closed
    until the promotion bundle is actually committed.
    """
    return dict(_load_runtime_promotion_receipts(spec=spec, planning_backend_declared=planning_backend_declared))

def _effective_planning_backend_profile_path() -> Path:
    env_path = os.environ.get('EMBODIED_ARM_PLANNING_BACKENDS_FILE', '').strip()
    return Path(env_path).expanduser() if env_path else PLANNING_BACKEND_PROFILE_PATH


def _load_planning_backend_declarations() -> dict[str, bool]:
    declarations = dict(_DEFAULT_BACKEND_DECLARATIONS)
    path = _effective_planning_backend_profile_path()
    if yaml is None or not path.exists():
        if _allow_generated_runtime_fallback():
            return declarations
        raise RuntimeError(f'planning backend profiles missing or yaml unavailable: {path}')
    try:
        raw = yaml.safe_load(path.read_text(encoding='utf-8')) or {}
    except Exception as exc:
        if _allow_generated_runtime_fallback():
            return declarations
        raise RuntimeError(f'failed to parse planning backend profiles: {path}: {exc}') from exc
    if not isinstance(raw, dict):
        if _allow_generated_runtime_fallback():
            return declarations
        raise RuntimeError(f'planning backend profiles must be a mapping: {path}')
    for name, payload in raw.items():
        if isinstance(payload, dict) and 'declared' in payload:
            declarations[str(name)] = bool(payload.get('declared', False))
    return declarations


def _resolve_backend_truthfulness(spec: RuntimeLaneSpec) -> RuntimeLaneSpec:
    if spec.planning_capability != 'validated_live' or not spec.planning_backend_profile:
        return spec
    declared = _load_planning_backend_declarations().get(spec.planning_backend_profile, False)
    backbone_declared = _validated_live_backbone_declared(spec, planning_backend_declared=declared)
    receipt_promoted = bool(_load_runtime_promotion_receipts(spec=spec, planning_backend_declared=declared).get('validated_live', False))
    if not declared or not backbone_declared or not receipt_promoted:
        return replace(
            spec,
            planning_backend_declared=bool(declared),
            public_runtime_tier='preview',
            task_workbench_visible=False,
            task_execution_interactive=False,
        )
    return replace(
        spec,
        planning_backend_declared=True,
        public_runtime_tier='validated_live',
        task_workbench_visible=True,
        task_execution_interactive=True,
    )


def runtime_lane_manifest() -> dict[str, dict[str, object]]:
    """Return the authoritative runtime-lane manifest.

    Returns:
        dict[str, dict[str, object]]: Plain-serializable runtime-lane map.

    Raises:
        Does not raise. YAML parse failures degrade to the in-module fallback map.
    """
    manifest: dict[str, dict[str, object]] = {}
    for name, spec in _load_runtime_lane_specs().items():
        manifest[name] = dict(_resolve_backend_truthfulness(spec).__dict__)
    return manifest


def normalize_runtime_lane(mode: str | None) -> str:
    normalized = (mode or 'sim_preview').strip().lower()
    normalized = RUNTIME_LANE_ALIASES.get(normalized, normalized)
    lane_specs = _load_runtime_lane_specs()
    return normalized if normalized in lane_specs else 'sim_preview'


def get_runtime_lane_spec(mode: str | None, *, include_mock_targets: bool = False) -> RuntimeLaneSpec:
    lane_specs = _load_runtime_lane_specs()
    base = lane_specs[normalize_runtime_lane(mode)]
    return _resolve_backend_truthfulness(RuntimeLaneSpec(
        name=base.name,
        simulate_hardware=base.simulate_hardware,
        camera_source=base.camera_source,
        esp32_mode=base.esp32_mode,
        include_mock_targets=include_mock_targets or base.include_mock_targets,
        mock_camera_profile=base.mock_camera_profile,
        enable_esp32_gateway=base.enable_esp32_gateway,
        esp32_base_url=base.esp32_base_url,
        enable_moveit=base.enable_moveit,
        enable_rviz=base.enable_rviz,
        enable_lifecycle_supervisor=base.enable_lifecycle_supervisor,
        enable_managed_lifecycle=base.enable_managed_lifecycle,
        autostart_managed_lifecycle=base.autostart_managed_lifecycle,
        allow_simulation_fallback=base.allow_simulation_fallback,
        planning_capability=base.planning_capability,
        planning_authoritative=base.planning_authoritative,
        planning_backend_name=base.planning_backend_name,
        planning_backend_profile=base.planning_backend_profile,
        scene_provider_mode=base.scene_provider_mode,
        grasp_provider_mode=base.grasp_provider_mode,
        esp32_stream_semantic=base.esp32_stream_semantic,
        esp32_frame_ingress_live=base.esp32_frame_ingress_live,
        frame_ingress_mode=base.frame_ingress_mode,
        forward_hardware_commands=base.forward_hardware_commands,
        hardware_execution_mode=base.hardware_execution_mode,
        execution_backbone=base.execution_backbone,
        execution_backbone_declared=base.execution_backbone_declared,
        stm32_authoritative_simulation=base.stm32_authoritative_simulation,
        enable_ros2_control=base.enable_ros2_control,
        planning_backend_declared=base.planning_backend_declared,
        public_runtime_tier=base.public_runtime_tier,
        task_workbench_visible=base.task_workbench_visible,
        task_execution_interactive=base.task_execution_interactive,
    ))




def _instantiate_action(factory, /, **kwargs):
    """Create a launch action and preserve keyword metadata for test stubs.

    Args:
        factory: Launch action class or callable.
        **kwargs: Constructor keyword arguments forwarded to the action.

    Returns:
        Instantiated launch action. When the underlying stub object does not retain
        constructor keywords, a ``kwargs`` attribute is attached for downstream
        inspection in tests.
    """
    action = factory(**kwargs)
    if not hasattr(action, 'kwargs'):
        try:
            setattr(action, 'kwargs', dict(kwargs))
        except Exception:
            pass
    return action

def _common_arguments(lane: RuntimeLaneSpec) -> tuple[list, dict[str, LaunchConfiguration]]:
    package_share = FindPackageShare('arm_bringup')
    defaults = {
        'calibration': PathJoinSubstitution([package_share, 'config', 'default_calibration.yaml']),
        'task_profile': PathJoinSubstitution([package_share, 'config', 'task_pick_by_color.yaml']),
        'placement_profile': PathJoinSubstitution([package_share, 'config', 'placement_profiles.yaml']),
        'safety_limits': PathJoinSubstitution([package_share, 'config', 'safety_limits.yaml']),
        'log_dir': 'logs',
        'stm32_port': '/dev/ttyUSB0',
        'camera_source': 'auto',
        'mock_camera_profile': lane.mock_camera_profile,
        'esp32_stream_endpoint': 'http://esp32.local/stream',
        'esp32_base_url': lane.esp32_base_url,
        'enable_moveit': 'true' if lane.enable_moveit else 'false',
        'enable_rviz': 'true' if lane.enable_rviz else 'false',
        'enable_lifecycle_supervisor': 'true' if lane.enable_lifecycle_supervisor else 'false',
        'enable_managed_lifecycle': 'true' if lane.enable_managed_lifecycle else 'false',
        'autostart_managed_lifecycle': 'true' if lane.autostart_managed_lifecycle else 'false',
        'allow_simulation_fallback': 'true' if lane.allow_simulation_fallback else 'false',
        'planning_capability': lane.planning_capability,
        'planning_authoritative': 'true' if lane.planning_authoritative else 'false',
        'planning_backend_name': lane.planning_backend_name,
        'planning_backend_profile': lane.planning_backend_profile,
        'planning_backend_config_path': str(_effective_planning_backend_profile_path()),
        'scene_provider_mode': lane.scene_provider_mode,
        'grasp_provider_mode': lane.grasp_provider_mode,
        'esp32_stream_semantic': lane.esp32_stream_semantic,
        'esp32_frame_ingress_live': 'true' if lane.esp32_frame_ingress_live else 'false',
        'frame_ingress_mode': lane.frame_ingress_mode,
        'forward_hardware_commands': 'true' if lane.forward_hardware_commands else 'false',
        'hardware_execution_mode': lane.hardware_execution_mode,
        'execution_backbone': lane.execution_backbone,
        'execution_backbone_declared': 'true' if lane.execution_backbone_declared else 'false',
        'stm32_authoritative_simulation': 'true' if lane.stm32_authoritative_simulation else 'false',
        'enable_ros2_control': 'true' if lane.enable_ros2_control else 'false',
        'planning_backend_declared': 'true' if lane.planning_backend_declared else 'false',
        'public_runtime_tier': lane.public_runtime_tier,
        'task_workbench_visible': '' if lane.task_workbench_visible is None else ('true' if lane.task_workbench_visible else 'false'),
        'task_execution_interactive': '' if lane.task_execution_interactive is None else ('true' if lane.task_execution_interactive else 'false'),
    }
    declarations = [DeclareLaunchArgument(name, default_value=value) for name, value in defaults.items()]
    return declarations, {name: LaunchConfiguration(name) for name in defaults}


def _managed_node(*, package: str, executable: str, name: str, parameters: list | None = None, condition=None):
    return _instantiate_action(LifecycleNode, package=package, executable=executable, name=name, parameters=parameters or [], output='screen', condition=condition)


def _regular_node(*, package: str, executable: str, name: str, parameters: list | None = None, condition=None):
    return _instantiate_action(Node, package=package, executable=executable, name=name, parameters=parameters or [], output='screen', condition=condition)


def _node_actions(*, enable_managed_lifecycle, package: str, executable: str, name: str, parameters: list | None = None):
    managed_condition = IfCondition(enable_managed_lifecycle)
    regular_condition = IfCondition(PythonExpression(['not ', enable_managed_lifecycle]))
    return [
        _managed_node(package=package, executable=executable, name=name, parameters=parameters, condition=managed_condition),
        _regular_node(package=package, executable=executable, name=name, parameters=parameters, condition=regular_condition),
    ]


def _supervision_nodes(*, enable_lifecycle_supervisor, enable_managed_lifecycle, autostart_managed_lifecycle) -> list:
    return [
        _instantiate_action(Node, package='arm_lifecycle_manager', executable='managed_lifecycle_manager_node', name='managed_lifecycle_manager_node', parameters=[{'autostart': autostart_managed_lifecycle}], condition=IfCondition(enable_managed_lifecycle), output='screen'),
        _instantiate_action(Node, package='arm_lifecycle_manager', executable='runtime_supervisor_node', name='runtime_supervisor_node', condition=IfCondition(enable_lifecycle_supervisor), output='screen'),
    ]


def _runtime_core_nodes(*, configs: dict[str, LaunchConfiguration], lane: RuntimeLaneSpec) -> list:
    task_profile = configs['task_profile']
    placement_profile = configs['placement_profile']
    calibration = configs['calibration']
    safety_limits = configs['safety_limits']
    log_dir = configs['log_dir']
    stm32_port = configs['stm32_port']
    esp32_stream = configs['esp32_stream_endpoint']
    esp32_base_url = configs['esp32_base_url']
    enable_moveit = configs['enable_moveit']
    enable_rviz = configs['enable_rviz']
    enable_lifecycle_supervisor = configs['enable_lifecycle_supervisor']
    enable_managed_lifecycle = configs['enable_managed_lifecycle']
    autostart_managed_lifecycle = configs['autostart_managed_lifecycle']
    allow_simulation_fallback = configs['allow_simulation_fallback']
    mock_camera_profile = configs['mock_camera_profile']
    planning_capability = configs['planning_capability']
    planning_authoritative = configs['planning_authoritative']
    planning_backend_name = configs['planning_backend_name']
    planning_backend_profile = configs['planning_backend_profile']
    planning_backend_config_path = configs['planning_backend_config_path']
    scene_provider_mode = configs['scene_provider_mode']
    grasp_provider_mode = configs['grasp_provider_mode']
    esp32_stream_semantic = configs['esp32_stream_semantic']
    esp32_frame_ingress_live = configs['esp32_frame_ingress_live']
    frame_ingress_mode = configs['frame_ingress_mode']
    forward_hardware_commands = configs['forward_hardware_commands']
    hardware_execution_mode = configs['hardware_execution_mode']
    stm32_authoritative_simulation = configs['stm32_authoritative_simulation']
    enable_ros2_control = configs['enable_ros2_control']
    resolved_camera_source = lane.camera_source if lane.camera_source != 'auto' else configs['camera_source']

    moveit_share = FindPackageShare('arm_moveit_config')
    description_share = FindPackageShare('arm_description')
    control_share = FindPackageShare('arm_control_bringup')

    nodes: list = [
        IncludeLaunchDescription(
            PythonLaunchDescriptionSource(PathJoinSubstitution([description_share, 'launch', 'description.launch.py'])),
            launch_arguments={'publish_robot_description': 'true'}.items(),
        ),
        IncludeLaunchDescription(
            PythonLaunchDescriptionSource(PathJoinSubstitution([control_share, 'launch', 'ros2_control.launch.py'])),
            condition=IfCondition(enable_ros2_control),
            launch_arguments={
                'use_fake_hardware': 'true' if lane.simulate_hardware else 'false',
                'controller_config': PathJoinSubstitution([control_share, 'config', 'controllers.yaml']),
                'hardware_plugin': 'arm_hardware_interface/EmbodiedArmSystemInterface',
            }.items(),
        ),
        IncludeLaunchDescription(
            PythonLaunchDescriptionSource(PathJoinSubstitution([moveit_share, 'launch', 'demo.launch.py'])),
            condition=IfCondition(enable_moveit),
            launch_arguments={'enable_rviz': enable_rviz}.items(),
        ),
        *_node_actions(enable_managed_lifecycle=enable_managed_lifecycle, package='arm_profiles', executable='profile_manager_node', name='profile_manager_node', parameters=[{'task_profile_path': task_profile, 'placement_profile_path': placement_profile}]),
        *_node_actions(enable_managed_lifecycle=enable_managed_lifecycle, package='arm_calibration', executable='calibration_manager_node', name='calibration_manager_node', parameters=[{'config_path': calibration}]),
        *_node_actions(enable_managed_lifecycle=enable_managed_lifecycle, package='arm_hardware_bridge', executable='stm32_serial_node', name='stm32_serial_node', parameters=[{'port': stm32_port if not lane.simulate_hardware else 'sim://stm32', 'baudrate': 115200, 'simulate_hardware': lane.simulate_hardware, 'allow_simulation_fallback': allow_simulation_fallback if not lane.simulate_hardware else 'false', 'authoritative_simulation': stm32_authoritative_simulation, 'execution_mode': hardware_execution_mode}]),
        *_node_actions(enable_managed_lifecycle=enable_managed_lifecycle, package='arm_hardware_bridge', executable='esp32_link_node', name='esp32_link_node', parameters=[{'mode': lane.esp32_mode, 'stream_endpoint': esp32_stream if not lane.simulate_hardware else 'sim://camera', 'stream_semantic': esp32_stream_semantic, 'frame_ingress_live': esp32_frame_ingress_live, 'frame_ingress_mode': frame_ingress_mode}]),
        *_node_actions(enable_managed_lifecycle=enable_managed_lifecycle, package='arm_hardware_bridge', executable='hardware_state_aggregator_node', name='hardware_state_aggregator_node'),
        *_node_actions(enable_managed_lifecycle=enable_managed_lifecycle, package='arm_hardware_bridge', executable='hardware_command_dispatcher_node', name='hardware_command_dispatcher', parameters=[{'safety_limits_path': safety_limits}]),
        *_node_actions(enable_managed_lifecycle=enable_managed_lifecycle, package='arm_readiness_manager', executable='readiness_manager_node', name='readiness_manager'),
        *_node_actions(enable_managed_lifecycle=enable_managed_lifecycle, package='arm_safety_supervisor', executable='safety_supervisor_node', name='safety_supervisor'),
        *_node_actions(enable_managed_lifecycle=enable_managed_lifecycle, package='arm_camera_driver', executable='camera_driver', name='camera_driver_node', parameters=[{'source_type': resolved_camera_source, 'mock_profile': mock_camera_profile, 'frame_ingress_mode': frame_ingress_mode}]),
        *_node_actions(enable_managed_lifecycle=enable_managed_lifecycle, package='arm_perception', executable='perception_node', name='perception_node'),
        *_node_actions(enable_managed_lifecycle=enable_managed_lifecycle, package='arm_motion_planner', executable='motion_planner_node', name='motion_planner_node', parameters=[{'planning_capability': planning_capability, 'planning_authoritative': planning_authoritative, 'planning_backend_name': planning_backend_name, 'planning_backend_profile': planning_backend_profile, 'planning_backend_config_path': planning_backend_config_path, 'scene_provider_mode': scene_provider_mode, 'grasp_provider_mode': grasp_provider_mode}]),
        *_node_actions(enable_managed_lifecycle=enable_managed_lifecycle, package='arm_motion_executor', executable='motion_executor_node', name='motion_executor_node', parameters=[{'forward_hardware_commands': forward_hardware_commands, 'hardware_execution_mode': hardware_execution_mode, 'safety_limits_path': safety_limits}]),
        *_node_actions(enable_managed_lifecycle=enable_managed_lifecycle, package='arm_task_orchestrator', executable='task_orchestrator_node', name='task_orchestrator', parameters=[{'task_profile_path': task_profile}]),
        *_node_actions(enable_managed_lifecycle=enable_managed_lifecycle, package='arm_diagnostics', executable='diagnostics_summary_node', name='diagnostics_summary'),
        *_node_actions(enable_managed_lifecycle=enable_managed_lifecycle, package='arm_logger', executable='event_logger_node', name='event_logger_node', parameters=[{'log_dir': log_dir}]),
        *_node_actions(enable_managed_lifecycle=enable_managed_lifecycle, package='arm_logger', executable='metrics_logger_node', name='metrics_logger_node', parameters=[{'log_dir': log_dir}]),
        *_supervision_nodes(enable_lifecycle_supervisor=enable_lifecycle_supervisor, enable_managed_lifecycle=enable_managed_lifecycle, autostart_managed_lifecycle=autostart_managed_lifecycle),
    ]
    if lane.scene_provider_mode == 'runtime_service':
        nodes.extend(_node_actions(enable_managed_lifecycle=enable_managed_lifecycle, package='arm_scene_manager', executable='scene_manager', name='scene_manager'))
    if lane.grasp_provider_mode == 'runtime_service':
        nodes.extend(_node_actions(enable_managed_lifecycle=enable_managed_lifecycle, package='arm_grasp_planner', executable='grasp_planner', name='grasp_planner'))
    if lane.enable_esp32_gateway:
        nodes.extend(_node_actions(enable_managed_lifecycle=enable_managed_lifecycle, package='arm_esp32_gateway', executable='esp32_gateway_node', name='esp32_gateway_node', parameters=[{'base_url': esp32_base_url}]))
    if lane.include_mock_targets:
        nodes.append(_instantiate_action(Node, package='arm_mock_tools', executable='mock_target_publisher_node', name='legacy_mock_target_publisher'))
    return nodes


def _experimental_nodes() -> list:
    return []


def build_runtime_launch_description(mode: str = 'sim_preview', *, include_mock_targets: bool = False) -> LaunchDescription:
    lane = get_runtime_lane_spec(mode, include_mock_targets=include_mock_targets)
    declarations, configs = _common_arguments(lane)
    nodes = _runtime_core_nodes(configs=configs, lane=lane)
    if lane.name in {'full_demo_preview', 'full_demo_authoritative'}:
        nodes.extend(_experimental_nodes())
    actions = [*declarations, *nodes]
    try:
        description = LaunchDescription(actions)
        if isinstance(description, list) or hasattr(description, '__iter__'):
            return description
    except TypeError:
        description = LaunchDescription()
    if hasattr(description, 'add_action'):
        for action in actions:
            description.add_action(action)
        return description
    if hasattr(description, 'append'):
        for action in actions:
            description.append(action)
        return description
    return actions


def build_launch_description(mode: str = 'sim_preview', *, include_mock_targets: bool = False) -> LaunchDescription:
    return build_runtime_launch_description(mode, include_mock_targets=include_mock_targets)


def build_official_runtime_launch_description(mode: str = 'sim_preview', *, include_mock_targets: bool = False) -> LaunchDescription:
    """Compatibility wrapper for the historic official_runtime alias.

    Args:
        mode: Requested lane or alias. `official_runtime` maps to the explicit `sim_preview` lane.
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
