from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

try:
    import yaml
except Exception:  # pragma: no cover
    yaml = None

from .moveit_client import PlanResult, PlanningRequest

DEFAULT_BACKEND_PROFILE_NAME = 'validated_sim_default'
DEFAULT_BACKEND_CONFIG_PATH = (
    Path(__file__).resolve().parents[2] / 'arm_bringup' / 'config' / 'planning_backend_profiles.yaml'
)


@dataclass(frozen=True)
class PlanningBackendProfile:
    """Declarative description of a planning backend.

    Args:
        name: Stable profile identifier.
        plugin: Backend plugin type such as ``deterministic_simulation`` or ``http_bridge``.
        declared: Whether the backend is intentionally declared for runtime use.
        capability_mode: Capability supported by the profile.
        planner_plugin: Planner plugin label published in summaries.
        scene_source: Planning-scene source label published in summaries.
        url: Optional HTTP bridge endpoint.
        timeout_sec: HTTP timeout in seconds.
        workspace_bounds: Cartesian workspace bounds for deterministic simulation.
        named_poses: Allowed named poses for deterministic simulation.
        metadata: Additional serializable profile metadata.

    Returns:
        None.

    Raises:
        Does not raise directly. Validation happens during profile loading.
    """

    name: str
    plugin: str
    declared: bool
    capability_mode: str
    planner_plugin: str
    scene_source: str
    url: str = ''
    timeout_sec: float = 1.5
    workspace_bounds: dict[str, float] = field(default_factory=dict)
    named_poses: dict[str, dict[str, float]] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ResolvedPlanningBackend:
    """Resolved backend callable and metadata used by the motion planner node."""

    backend: Callable[[PlanningRequest], PlanResult] | None
    declared: bool
    profile_name: str
    planner_plugin: str
    scene_source: str
    metadata: dict[str, Any] = field(default_factory=dict)


_BUILTIN_PROFILES: dict[str, PlanningBackendProfile] = {
    'validated_sim_default': PlanningBackendProfile(
        name='validated_sim_default',
        plugin='deterministic_simulation',
        declared=True,
        capability_mode='validated_sim',
        planner_plugin='pilz_industrial_motion_planner',
        scene_source='runtime_scene_service',
        workspace_bounds={
            'min_x': -0.35,
            'max_x': 0.35,
            'min_y': -0.35,
            'max_y': 0.35,
            'min_z': 0.02,
            'max_z': 0.45,
            'min_yaw': -3.14159,
            'max_yaw': 3.14159,
            'approach_offset_z': 0.08,
        },
        named_poses={
            'home': {'joint_1': 0.0, 'joint_2': 0.0, 'joint_3': 0.0, 'joint_4': 0.0, 'joint_5': 0.0, 'joint_6': 0.0},
            'stow': {'joint_1': 0.0, 'joint_2': -0.35, 'joint_3': 0.7, 'joint_4': 0.0, 'joint_5': 0.55, 'joint_6': 0.0},
            'inspect': {'joint_1': 0.0, 'joint_2': -0.1, 'joint_3': 0.35, 'joint_4': 0.0, 'joint_5': 0.2, 'joint_6': 0.0},
        },
        metadata={'executionModel': 'validated_simulation_runtime'},
    ),
    'validated_live_bridge': PlanningBackendProfile(
        name='validated_live_bridge',
        plugin='http_bridge',
        declared=False,
        capability_mode='validated_live',
        planner_plugin='moveit_http_bridge',
        scene_source='runtime_scene_service',
        url='http://127.0.0.1:8088/plan',
        timeout_sec=1.5,
        metadata={'executionModel': 'validated_live_bridge'},
    ),
}


class DeterministicSimulationBackend:
    """Deterministic validated-simulation planning backend.

    The backend is not an echo-only path. It performs explicit workspace
    validation, named-pose validation, and generates a multi-waypoint
    simulation trajectory suitable for authoritative repository validation.
    """

    def __init__(self, profile: PlanningBackendProfile, backend_name: str) -> None:
        self._profile = profile
        self._backend_name = backend_name

    def __call__(self, request: PlanningRequest) -> PlanResult:
        try:
            trajectory = self._build_trajectory(request)
            return PlanResult(
                accepted=True,
                success=True,
                planner_plugin=self._profile.planner_plugin,
                scene_source=self._profile.scene_source,
                request_kind=request.request_kind,
                trajectory=trajectory,
                planning_time_sec=0.018,
                request=request,
                authoritative=True,
                capability_mode='validated_sim',
                backend_name=self._backend_name,
                metadata={
                    'planningCapability': 'validated_sim',
                    'planningAuthoritative': True,
                    'planningBackend': self._backend_name,
                    'planningBackendReady': True,
                    'backendProfile': self._profile.name,
                    **dict(self._profile.metadata or {}),
                },
            )
        except ValueError as exc:
            return PlanResult(
                accepted=True,
                success=False,
                planner_plugin=self._profile.planner_plugin,
                scene_source=self._profile.scene_source,
                request_kind=request.request_kind,
                trajectory={},
                planning_time_sec=0.0,
                error_code='planning_request_invalid',
                error_message=str(exc),
                request=request,
                authoritative=True,
                capability_mode='validated_sim',
                backend_name=self._backend_name,
                metadata={
                    'planningCapability': 'validated_sim',
                    'planningAuthoritative': True,
                    'planningBackend': self._backend_name,
                    'planningBackendReady': True,
                    'backendProfile': self._profile.name,
                },
            )

    def _build_trajectory(self, request: PlanningRequest) -> dict[str, Any]:
        if request.request_kind == 'named_pose':
            named_pose = str(request.target.get('named_pose', '')).strip()
            if named_pose not in self._profile.named_poses:
                raise ValueError(f'unsupported validated-sim named pose: {named_pose}')
            return {
                'requestKind': request.request_kind,
                'frame': request.frame,
                'target': dict(request.target),
                'executionModel': self._profile.metadata.get('executionModel', 'validated_simulation_runtime'),
                'waypoints': [
                    {'phase': 'joint_seed', 'joints': dict(self._profile.named_poses['home'])},
                    {'phase': 'joint_goal', 'joints': dict(self._profile.named_poses[named_pose])},
                ],
            }
        pose = self._extract_pose(request)
        self._validate_pose(pose)
        approach_offset = float(self._profile.workspace_bounds.get('approach_offset_z', 0.08))
        approach_pose = dict(pose)
        approach_pose['z'] = min(
            float(self._profile.workspace_bounds.get('max_z', approach_pose['z'] + approach_offset)),
            pose['z'] + approach_offset,
        )
        waypoints = [
            {'phase': 'seed', 'pose': {'x': 0.0, 'y': 0.0, 'z': max(pose['z'], 0.12), 'yaw': 0.0}},
            {'phase': 'approach', 'pose': approach_pose},
            {'phase': 'goal', 'pose': pose},
        ]
        if request.request_kind == 'stage' and request.target.get('stage') == 'retreat':
            retreat_pose = dict(approach_pose)
            retreat_pose['z'] = min(retreat_pose['z'] + 0.04, float(self._profile.workspace_bounds.get('max_z', retreat_pose['z'] + 0.04)))
            waypoints.append({'phase': 'retreat', 'pose': retreat_pose})
        return {
            'requestKind': request.request_kind,
            'frame': request.frame,
            'target': dict(request.target),
            'executionModel': self._profile.metadata.get('executionModel', 'validated_simulation_runtime'),
            'waypoints': waypoints,
        }

    def _extract_pose(self, request: PlanningRequest) -> dict[str, float]:
        target = request.target
        pose_payload = target.get('pose') if isinstance(target.get('pose'), dict) else target
        if not isinstance(pose_payload, dict):
            raise ValueError('validated-sim request must provide pose fields')
        return {
            'x': float(pose_payload.get('x', 0.0)),
            'y': float(pose_payload.get('y', 0.0)),
            'z': float(pose_payload.get('z', 0.0)),
            'yaw': float(pose_payload.get('yaw', 0.0)),
        }

    def _validate_pose(self, pose: dict[str, float]) -> None:
        bounds = self._profile.workspace_bounds
        checks = {
            'x': (bounds.get('min_x'), bounds.get('max_x')),
            'y': (bounds.get('min_y'), bounds.get('max_y')),
            'z': (bounds.get('min_z'), bounds.get('max_z')),
            'yaw': (bounds.get('min_yaw'), bounds.get('max_yaw')),
        }
        for axis, (lower, upper) in checks.items():
            value = float(pose[axis])
            if lower is not None and value < float(lower):
                raise ValueError(f'pose {axis} below workspace lower bound: {value}')
            if upper is not None and value > float(upper):
                raise ValueError(f'pose {axis} above workspace upper bound: {value}')


class HttpPlanningBackend:
    """HTTP bridge backend for validated-live planning.

    The bridge expects a JSON POST endpoint that accepts normalized planning
    requests and returns a JSON body matching the fields consumed below.
    """

    def __init__(self, profile: PlanningBackendProfile, backend_name: str) -> None:
        self._profile = profile
        self._backend_name = backend_name

    def __call__(self, request: PlanningRequest) -> PlanResult:
        if not self._profile.url:
            return self._unavailable_result(request, error_message='validated-live backend URL not configured')
        payload = {
            'requestKind': request.request_kind,
            'frame': request.frame,
            'target': request.target,
            'constraints': request.constraints,
            'metadata': request.metadata,
            'capabilityMode': self._profile.capability_mode,
            'backendProfile': self._profile.name,
        }
        encoded = json.dumps(payload, ensure_ascii=False).encode('utf-8')
        http_request = urllib.request.Request(
            self._profile.url,
            data=encoded,
            headers={'Content-Type': 'application/json'},
            method='POST',
        )
        try:
            with urllib.request.urlopen(http_request, timeout=max(0.1, float(self._profile.timeout_sec))) as response:
                raw = response.read().decode('utf-8')
            body = json.loads(raw) if raw else {}
        except (urllib.error.URLError, TimeoutError, OSError, ValueError, json.JSONDecodeError) as exc:
            return self._unavailable_result(request, error_message=f'validated-live planning bridge unavailable: {exc}')
        if not isinstance(body, dict):
            return self._unavailable_result(request, error_message='validated-live planning bridge returned non-object payload')
        accepted = bool(body.get('accepted', False))
        success = bool(body.get('success', False))
        trajectory = dict(body.get('trajectory') or {})
        return PlanResult(
            accepted=accepted,
            success=success,
            planner_plugin=str(body.get('planner_plugin', self._profile.planner_plugin)),
            scene_source=str(body.get('scene_source', self._profile.scene_source)),
            request_kind=request.request_kind,
            trajectory=trajectory,
            planning_time_sec=float(body.get('planning_time_sec', 0.0)),
            error_code=str(body.get('error_code', '')),
            error_message=str(body.get('error_message', '')),
            request=request,
            authoritative=accepted and success,
            capability_mode='validated_live',
            backend_name=self._backend_name,
            metadata={
                'planningCapability': 'validated_live',
                'planningAuthoritative': accepted and success,
                'planningBackend': self._backend_name,
                'planningBackendReady': accepted or success,
                'backendProfile': self._profile.name,
                **dict(self._profile.metadata or {}),
                **dict(body.get('metadata') or {}),
            },
        )

    def _unavailable_result(self, request: PlanningRequest, *, error_message: str) -> PlanResult:
        return PlanResult(
            accepted=False,
            success=False,
            planner_plugin=self._profile.planner_plugin,
            scene_source=self._profile.scene_source,
            request_kind=request.request_kind,
            trajectory={},
            planning_time_sec=0.0,
            error_code='planning_bridge_unavailable',
            error_message=error_message,
            request=request,
            authoritative=False,
            capability_mode='validated_live',
            backend_name=self._backend_name,
            metadata={
                'planningCapability': 'validated_live',
                'planningAuthoritative': False,
                'planningBackend': self._backend_name,
                'planningBackendReady': False,
                'backendProfile': self._profile.name,
                **dict(self._profile.metadata or {}),
            },
        )




def effective_backend_config_path(config_path: str | os.PathLike[str] | None = None) -> Path:
    """Resolve the backend-profile configuration path.

    Args:
        config_path: Explicit path override.

    Returns:
        Path: Existing or prospective backend-profile configuration path.

    Raises:
        Does not raise. Missing files are handled by the callers.
    """
    if config_path:
        return Path(config_path).expanduser()
    env_path = os.environ.get('EMBODIED_ARM_PLANNING_BACKENDS_FILE', '').strip()
    if env_path:
        return Path(env_path).expanduser()
    return DEFAULT_BACKEND_CONFIG_PATH


def load_backend_profiles(config_path: str | os.PathLike[str] | None = None) -> dict[str, PlanningBackendProfile]:
    """Load planning-backend profiles from the generated configuration artifact.

    Args:
        config_path: Optional YAML/JSON file path.

    Returns:
        dict[str, PlanningBackendProfile]: Profiles materialized from the
        generated backend configuration.

    Raises:
        RuntimeError: The generated configuration file is missing, parsing fails,
            YAML support is unavailable for YAML input, or the payload is not a
            mapping.

    Boundary behavior:
        Production/runtime validation must not silently fall back to baked-in live
        profiles because that would hide authority/config drift. Missing or
        malformed artifacts therefore fail fast.
    """
    profiles: dict[str, PlanningBackendProfile] = {}
    path = effective_backend_config_path(config_path)
    if not path.exists():
        raise RuntimeError(f'planning backend profile file missing: {path}')
    try:
        raw_text = path.read_text(encoding='utf-8')
        if path.suffix.lower() == '.json':
            payload = json.loads(raw_text)
        else:
            if yaml is None:
                raise RuntimeError('yaml support unavailable for planning backend profiles')
            payload = yaml.safe_load(raw_text)
    except Exception as exc:
        raise RuntimeError(f'failed to load planning backend profiles: {path}: {exc}') from exc
    if not isinstance(payload, dict):
        raise RuntimeError(f'planning backend profiles must be a mapping: {path}')
    for name, item in payload.items():
        if not isinstance(item, dict):
            continue
        profile_name = str(name).strip()
        if not profile_name:
            continue
        profiles[profile_name] = PlanningBackendProfile(
            name=profile_name,
            plugin=str(item.get('plugin', 'deterministic_simulation')),
            declared=bool(item.get('declared', False)),
            capability_mode=str(item.get('capability_mode', 'validated_sim')),
            planner_plugin=str(item.get('planner_plugin', 'ompl')),
            scene_source=str(item.get('scene_source', 'planning_scene')),
            url=str(item.get('url', '')),
            timeout_sec=float(item.get('timeout_sec', 1.5)),
            workspace_bounds=dict(item.get('workspace_bounds') or {}),
            named_poses={str(key): dict(value or {}) for key, value in dict(item.get('named_poses') or {}).items()},
            metadata=dict(item.get('metadata') or {}),
        )
    return profiles


def resolve_planning_backend(
    *,
    capability_mode: str,
    backend_name: str,
    backend_profile: str = '',
    backend_config_path: str = '',
) -> ResolvedPlanningBackend:
    """Resolve the runtime planning backend.

    Args:
        capability_mode: Requested planning capability.
        backend_name: Stable backend identifier published to runtime clients.
        backend_profile: Optional backend profile name.
        backend_config_path: Optional profile configuration path.

    Returns:
        ResolvedPlanningBackend: Backend callable and associated metadata.

    Raises:
        ValueError: If the requested profile exists but is incompatible with the capability mode.

    Boundary behavior:
        ``validated_live`` without a declared compatible profile resolves to
        ``backend=None`` so the planner remains fail-closed.
    """
    normalized_capability = str(capability_mode or 'contract_only').strip().lower() or 'contract_only'
    profile_name = str(backend_profile or '').strip()
    if not profile_name:
        if normalized_capability == 'validated_sim':
            profile_name = DEFAULT_BACKEND_PROFILE_NAME
        else:
            return ResolvedPlanningBackend(
                backend=None,
                declared=False,
                profile_name='',
                planner_plugin='ompl',
                scene_source='planning_scene',
                metadata={},
            )
    profiles = load_backend_profiles(backend_config_path)
    profile = profiles.get(profile_name)
    if profile is None:
        return ResolvedPlanningBackend(
            backend=None,
            declared=False,
            profile_name=profile_name,
            planner_plugin='ompl',
            scene_source='planning_scene',
            metadata={'profileMissing': True},
        )
    if profile.capability_mode != normalized_capability:
        raise ValueError(
            f'planning backend profile {profile.name!r} supports {profile.capability_mode!r}, '
            f'not {normalized_capability!r}'
        )
    backend_callable: Callable[[PlanningRequest], PlanResult] | None
    if profile.plugin == 'deterministic_simulation':
        backend_callable = DeterministicSimulationBackend(profile, backend_name=backend_name)
    elif profile.plugin == 'http_bridge' and profile.declared:
        backend_callable = HttpPlanningBackend(profile, backend_name=backend_name)
    elif profile.plugin == 'http_bridge':
        backend_callable = None
    else:
        raise ValueError(f'unsupported planning backend plugin: {profile.plugin!r}')
    return ResolvedPlanningBackend(
        backend=backend_callable,
        declared=profile.declared,
        profile_name=profile.name,
        planner_plugin=profile.planner_plugin,
        scene_source=profile.scene_source,
        metadata=dict(profile.metadata or {}),
    )
