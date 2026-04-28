from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any, Callable

from .errors import PlanningFailedError, PlanningUnavailableError, SceneUnavailableError

PLANNING_CAPABILITY_MODES = frozenset({'disabled', 'contract_only', 'validated_sim', 'validated_live'})


@dataclass(frozen=True)
class PlanningRequest:
    """Normalized planning request consumed by the runtime adapter.

    Args:
        request_kind: Logical planning request type such as ``named_pose`` or ``pose_goal``.
        frame: Reference frame associated with the request.
        target: Normalized target payload expected by the backend.
        constraints: Optional planning constraints.
        metadata: Optional request metadata for tracing and audit.

    Returns:
        None.

    Raises:
        Does not raise directly. Validation occurs in :class:`MoveItClient` methods.
    """

    request_kind: str
    frame: str
    target: dict[str, Any]
    constraints: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SceneState:
    """Serializable planning-scene snapshot used by runtime-facing layers."""

    available: bool
    source: str
    objects: tuple[dict[str, Any], ...] = ()
    frame: str = 'world'
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PlanResult:
    """Normalized planning response returned by the runtime adapter."""

    accepted: bool
    success: bool
    planner_plugin: str
    scene_source: str
    request_kind: str
    trajectory: dict[str, Any] = field(default_factory=dict)
    planning_time_sec: float = 0.0
    error_code: str = ''
    error_message: str = ''
    request: PlanningRequest | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    authoritative: bool = False
    capability_mode: str = 'contract_only'
    backend_name: str = 'fallback_contract'


class MoveItClient:
    """Runtime-facing planning adapter with truthful capability semantics.

    The adapter deliberately distinguishes between contract-only fallback
    planning and validated authoritative planning. Callers can still request
    contract-only plans for preview/test flows, but readiness and execution
    layers must inspect ``authoritative`` and ``capability_mode`` rather than
    assuming ``success=True`` implies a live MoveIt stack is available.
    """

    def __init__(
        self,
        planner_plugin: str = 'ompl',
        scene_source: str = 'planning_scene',
        *,
        planning_backend: Callable[[PlanningRequest], PlanResult] | None = None,
        scene_provider: Callable[[], SceneState] | None = None,
        capability_mode: str = 'contract_only',
        authoritative: bool | None = None,
        backend_name: str | None = None,
    ) -> None:
        """Initialize the planning adapter.

        Args:
            planner_plugin: Planner plugin identifier reported in results.
            scene_source: Scene source identifier reported in results.
            planning_backend: Optional injected runtime backend.
            scene_provider: Optional injected planning-scene provider.
            capability_mode: Stable capability token. Supported values are
                ``disabled``, ``contract_only``, ``validated_sim``, and
                ``validated_live``.
            authoritative: Optional override for the result-authority flag.
            backend_name: Stable backend identifier reported in results.

        Returns:
            None.

        Raises:
            ValueError: If required inputs are empty or ``capability_mode`` is unsupported.
        """
        if not planner_plugin:
            raise ValueError('planner_plugin must be non-empty')
        if not scene_source:
            raise ValueError('scene_source must be non-empty')
        capability = str(capability_mode or 'contract_only').strip().lower()
        if capability not in PLANNING_CAPABILITY_MODES:
            raise ValueError(f'unsupported planning capability mode: {capability_mode!r}')
        self.planner_plugin = planner_plugin
        self.scene_source = scene_source
        self.capability_mode = capability
        self.authoritative = self._capability_is_authoritative(capability) if authoritative is None else bool(authoritative)
        self.backend_name = str(backend_name or self._default_backend_name(capability, planning_backend is not None))
        if planning_backend is None:
            self._planning_backend = self._default_backend_for_capability(capability)
        else:
            self._planning_backend = planning_backend
        self._scene_provider = scene_provider or self._fallback_scene_provider

    @staticmethod
    def _default_backend_name(capability_mode: str, injected: bool) -> str:
        if injected:
            return 'injected_backend'
        if capability_mode == 'validated_sim':
            return 'validated_sim_runtime'
        if capability_mode == 'validated_live':
            return 'validated_live_bridge'
        return 'fallback_contract'

    def _default_backend_for_capability(self, capability_mode: str) -> Callable[[PlanningRequest], PlanResult]:
        """Return the built-in backend that matches the configured capability.

        Args:
            capability_mode: Stable planning capability token.

        Returns:
            Callable backend used by the planner.

        Raises:
            Does not raise. Unsupported modes degrade to the contract backend.
        """
        if capability_mode == 'validated_sim':
            return self._validated_sim_backend
        if capability_mode == 'validated_live':
            return self._validated_live_backend_unavailable
        return self._fallback_backend

    @staticmethod
    def _capability_is_authoritative(capability_mode: str) -> bool:
        return capability_mode in {'validated_sim', 'validated_live'}

    def planning_backend_ready(self) -> bool:
        """Return whether the configured planning backend is actually usable.

        Returns:
            bool: ``True`` when the backend can service requests without falling
            into the validated-live fail-closed path.

        Boundary behavior:
            ``validated_live`` reports not ready until an explicit backend is
            injected through ``planning_backend``.
        """
        backend = self._planning_backend
        unavailable = self._validated_live_backend_unavailable
        backend_func = getattr(backend, '__func__', backend)
        unavailable_func = getattr(unavailable, '__func__', unavailable)
        return backend_func is not unavailable_func

    def query_scene_state(self) -> SceneState:
        """Return the current planning-scene snapshot.

        Args:
            None.

        Returns:
            SceneState: Current scene information.

        Raises:
            SceneUnavailableError: If the scene provider reports the scene as unavailable.
        """
        state = self._scene_provider()
        if not state.available:
            raise SceneUnavailableError('planning scene unavailable')
        return state

    def plan_named_pose(self, pose_name: str, *, metadata: dict[str, Any] | None = None) -> PlanResult:
        """Plan to a named pose.

        Args:
            pose_name: Named pose identifier.
            metadata: Optional tracing metadata.

        Returns:
            PlanResult: Normalized planning response.

        Raises:
            ValueError: If pose_name is empty.
            PlanningUnavailableError: If no planning backend is available.
            PlanningFailedError: If the backend rejects the request.
            SceneUnavailableError: If the planning scene is unavailable.
        """
        if not str(pose_name).strip():
            raise ValueError('pose_name must be non-empty')
        request = PlanningRequest(
            request_kind='named_pose',
            frame='base_link',
            target={'named_pose': str(pose_name).strip()},
            metadata=dict(metadata or {}),
        )
        return self._execute_request(request)

    def plan_pose_goal(
        self,
        pose: dict[str, Any],
        *,
        frame: str = 'table',
        metadata: dict[str, Any] | None = None,
        constraints: dict[str, Any] | None = None,
    ) -> PlanResult:
        """Plan to a pose goal.

        Args:
            pose: Cartesian target payload.
            frame: Pose frame identifier.
            metadata: Optional tracing metadata.
            constraints: Optional planning constraints.

        Returns:
            PlanResult: Normalized planning response.

        Raises:
            ValueError: If ``pose`` or ``frame`` are invalid.
            PlanningUnavailableError: If no planning backend is available.
            PlanningFailedError: If the backend rejects the request.
            SceneUnavailableError: If the planning scene is unavailable.
        """
        if not isinstance(pose, dict) or not pose:
            raise ValueError('pose must be a non-empty dictionary')
        if not str(frame).strip():
            raise ValueError('frame must be non-empty')
        request = PlanningRequest(
            request_kind='pose_goal',
            frame=str(frame).strip(),
            target=dict(pose),
            constraints=dict(constraints or {}),
            metadata=dict(metadata or {}),
        )
        return self._execute_request(request)

    def plan_stage_request(self, stage: dict[str, Any], *, metadata: dict[str, Any] | None = None) -> PlanResult:
        """Plan from a normalized stage request.

        Args:
            stage: Normalized stage dictionary.
            metadata: Optional tracing metadata.

        Returns:
            PlanResult: Normalized planning response.

        Raises:
            ValueError: If ``stage`` is not a non-empty mapping.
            PlanningUnavailableError: If no planning backend is available.
            PlanningFailedError: If the backend rejects the request.
            SceneUnavailableError: If the planning scene is unavailable.
        """
        if not isinstance(stage, dict) or not stage:
            raise ValueError('stage must be a non-empty dictionary')
        frame = str(stage.get('frame', 'table')).strip() or 'table'
        request = PlanningRequest(
            request_kind='stage',
            frame=frame,
            target=dict(stage),
            metadata=dict(metadata or {}),
        )
        return self._execute_request(request)

    def map_planning_error(self, result: PlanResult) -> str:
        """Return a stable planner error classification."""
        if not isinstance(result, PlanResult):
            raise ValueError('result must be a PlanResult instance')
        if result.success:
            return 'ok'
        return result.error_code or 'planning_failed'

    def _normalize_result(self, result: PlanResult, request: PlanningRequest) -> PlanResult:
        backend_ready = result.accepted or result.success or self.planning_backend_ready()
        metadata = {
            **dict(request.metadata),
            **dict(result.metadata or {}),
            'planningCapability': self.capability_mode,
            'planningAuthoritative': bool(result.authoritative if result.authoritative is not None else self.authoritative),
            'planningBackend': str(result.backend_name or self.backend_name),
            'planningBackendReady': backend_ready,
            'plannerPlugin': result.planner_plugin or self.planner_plugin,
            'sceneSource': result.scene_source or self.scene_source,
        }
        authoritative = bool(result.authoritative)
        return replace(
            result,
            planner_plugin=result.planner_plugin or self.planner_plugin,
            scene_source=result.scene_source or self.scene_source,
            request=result.request or request,
            metadata=metadata,
            authoritative=authoritative,
            capability_mode=result.capability_mode or self.capability_mode,
            backend_name=result.backend_name or self.backend_name,
        )

    def _execute_request(self, request: PlanningRequest) -> PlanResult:
        """Execute a normalized request against the configured backend.

        Args:
            request: Normalized planning request.

        Returns:
            PlanResult: Successful normalized result.

        Raises:
            PlanningUnavailableError: If the capability is disabled or the
                backend rejects the request.
            PlanningFailedError: If the backend accepts but cannot generate a plan.
            SceneUnavailableError: If the scene provider reports no scene.
        """
        if self.capability_mode == 'disabled':
            raise PlanningUnavailableError('planning capability disabled')
        _ = self.query_scene_state()
        backend = self._planning_backend
        if backend is None:
            raise PlanningUnavailableError('planning backend unavailable')
        result = self._normalize_result(backend(request), request)
        if not result.accepted:
            raise PlanningUnavailableError(result.error_message or 'planning backend rejected request')
        if not result.success:
            raise PlanningFailedError(result.error_message or 'planning backend failed to produce plan')
        return result

    def _fallback_scene_provider(self) -> SceneState:
        """Return a deterministic fallback scene state."""
        return SceneState(
            available=True,
            source=self.scene_source,
            objects=(
                {'id': 'table', 'frame': 'world', 'shape': 'box'},
                {'id': 'workspace_guard', 'frame': 'world', 'shape': 'box'},
            ),
            frame='world',
            metadata={
                'providerMode': 'fallback_scene',
                'providerAuthoritative': False,
            },
        )

    def _fallback_backend(self, request: PlanningRequest) -> PlanResult:
        """Produce a deterministic contract-only plan result for tests and previews."""
        trajectory = {
            'requestKind': request.request_kind,
            'frame': request.frame,
            'target': dict(request.target),
            'waypoints': self._build_contract_waypoints(request),
            'executionModel': 'contract_preview',
        }
        return PlanResult(
            accepted=True,
            success=True,
            planner_plugin=self.planner_plugin,
            scene_source=self.scene_source,
            request_kind=request.request_kind,
            trajectory=trajectory,
            planning_time_sec=0.01,
            request=request,
            authoritative=False,
            capability_mode='contract_only',
            backend_name='fallback_contract',
            metadata={
                'planningCapability': 'contract_only',
                'planningAuthoritative': False,
                'planningBackend': 'fallback_contract',
                'planningBackendReady': True,
            },
        )

    def _validated_sim_backend(self, request: PlanningRequest) -> PlanResult:
        """Produce a deterministic validated-simulation planning result.

        The implementation is intentionally stricter than the preview fallback:
        it validates the target against explicit workspace bounds, validates
        named poses against a curated set, and produces a staged multi-waypoint
        trajectory representing a simulation-ready execution plan.

        Args:
            request: Normalized planning request.

        Returns:
            PlanResult: Accepted authoritative validated-simulation response.

        Raises:
            Does not raise directly. Invalid requests are encoded as failed
            :class:`PlanResult` instances and mapped by ``_execute_request``.
        """
        try:
            trajectory = {
                'requestKind': request.request_kind,
                'frame': request.frame,
                'target': dict(request.target),
                'waypoints': self._build_validated_sim_waypoints(request),
                'executionModel': 'validated_simulation_runtime',
            }
            return PlanResult(
                accepted=True,
                success=True,
                planner_plugin=self.planner_plugin,
                scene_source=self.scene_source,
                request_kind=request.request_kind,
                trajectory=trajectory,
                planning_time_sec=0.018,
                request=request,
                authoritative=True,
                capability_mode='validated_sim',
                backend_name='validated_sim_runtime',
                metadata={
                    'planningCapability': 'validated_sim',
                    'planningAuthoritative': True,
                    'planningBackend': 'validated_sim_runtime',
                    'planningBackendReady': True,
                },
            )
        except ValueError as exc:
            return PlanResult(
                accepted=True,
                success=False,
                planner_plugin=self.planner_plugin,
                scene_source=self.scene_source,
                request_kind=request.request_kind,
                trajectory={},
                planning_time_sec=0.0,
                error_code='planning_request_invalid',
                error_message=str(exc),
                request=request,
                authoritative=True,
                capability_mode='validated_sim',
                backend_name='validated_sim_runtime',
                metadata={
                    'planningCapability': 'validated_sim',
                    'planningAuthoritative': True,
                    'planningBackend': 'validated_sim_runtime',
                    'planningBackendReady': True,
                },
            )

    def _validated_live_backend_unavailable(self, request: PlanningRequest) -> PlanResult:
        """Return a fail-closed result for validated-live lanes without a live backend.

        Args:
            request: Normalized planning request.

        Returns:
            PlanResult: Rejected result that forces callers to surface planner
                unavailability instead of silently falling back.

        Raises:
            Does not raise. The caller maps the rejected result into
            ``PlanningUnavailableError``.
        """
        return PlanResult(
            accepted=False,
            success=False,
            planner_plugin=self.planner_plugin,
            scene_source=self.scene_source,
            request_kind=request.request_kind,
            trajectory={},
            planning_time_sec=0.0,
            error_code='planning_backend_unavailable',
            error_message='validated_live requires an injected live planning backend',
            request=request,
            authoritative=False,
            capability_mode='validated_live',
            backend_name='validated_live_bridge',
            metadata={
                'planningCapability': 'validated_live',
                'planningAuthoritative': False,
                'planningBackend': 'validated_live_bridge',
                'planningBackendReady': False,
            },
        )

    @staticmethod
    def _build_contract_waypoints(request: PlanningRequest) -> list[dict[str, Any]]:
        """Build deterministic preview waypoints from a normalized request."""
        if request.request_kind == 'named_pose':
            return [{'named_pose': request.target['named_pose']}]
        if request.request_kind in {'pose_goal', 'stage'}:
            return [dict(request.target)]
        return []

    def _build_validated_sim_waypoints(self, request: PlanningRequest) -> list[dict[str, Any]]:
        """Build multi-waypoint validated-simulation trajectories.

        Args:
            request: Normalized planning request.

        Returns:
            list[dict[str, Any]]: Ordered simulation waypoints.

        Raises:
            ValueError: If the request target violates the validated-sim bounds.

        Boundary behavior:
            Named poses are limited to the curated ``home``, ``stow`` and
            ``inspect`` set. Cartesian requests are clamped only through
            validation; out-of-bounds inputs are rejected instead of silently
            repaired.
        """
        if request.request_kind == 'named_pose':
            named_pose = str(request.target.get('named_pose', '')).strip()
            if named_pose not in {'home', 'stow', 'inspect'}:
                raise ValueError(f'unsupported validated-sim named pose: {named_pose}')
            return [
                {'phase': 'joint_seed', 'named_pose': 'home'},
                {'phase': 'joint_goal', 'named_pose': named_pose},
            ]
        pose = self._extract_pose_request(request)
        self._validate_pose_request(pose)
        approach = dict(pose)
        approach['z'] = min(0.45, pose['z'] + 0.08)
        waypoints = [
            {'phase': 'seed', 'pose': {'x': 0.0, 'y': 0.0, 'z': max(pose['z'], 0.12), 'yaw': 0.0}},
            {'phase': 'approach', 'pose': approach},
            {'phase': 'goal', 'pose': pose},
        ]
        if request.request_kind == 'stage' and request.target.get('stage') == 'retreat':
            retreat = dict(approach)
            retreat['z'] = min(0.45, retreat['z'] + 0.04)
            waypoints.append({'phase': 'retreat', 'pose': retreat})
        return waypoints

    @staticmethod
    def _extract_pose_request(request: PlanningRequest) -> dict[str, float]:
        target = request.target
        pose_payload = target.get('pose') if isinstance(target.get('pose'), dict) else target
        if not isinstance(pose_payload, dict):
            raise ValueError('validated-sim request must provide pose fields')
        try:
            return {
                'x': float(pose_payload.get('x', 0.0)),
                'y': float(pose_payload.get('y', 0.0)),
                'z': float(pose_payload.get('z', 0.0)),
                'yaw': float(pose_payload.get('yaw', 0.0)),
            }
        except (TypeError, ValueError) as exc:
            raise ValueError(f'invalid pose payload: {exc}') from exc

    @staticmethod
    def _validate_pose_request(pose: dict[str, float]) -> None:
        bounds = {
            'x': (-0.35, 0.35),
            'y': (-0.35, 0.35),
            'z': (0.02, 0.45),
            'yaw': (-3.14159, 3.14159),
        }
        for axis, (lower, upper) in bounds.items():
            value = float(pose[axis])
            if value < lower:
                raise ValueError(f'pose {axis} below workspace lower bound: {value}')
            if value > upper:
                raise ValueError(f'pose {axis} above workspace upper bound: {value}')
