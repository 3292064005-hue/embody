from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from .errors import PlanningFailedError, PlanningUnavailableError, SceneUnavailableError


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


class MoveItClient:
    """Runtime-facing planning adapter with stable fallback semantics."""

    def __init__(
        self,
        planner_plugin: str = 'ompl',
        scene_source: str = 'planning_scene',
        *,
        planning_backend: Callable[[PlanningRequest], PlanResult] | None = None,
        scene_provider: Callable[[], SceneState] | None = None,
    ) -> None:
        """Initialize the planning adapter.

        Args:
            planner_plugin: Planner plugin identifier reported in results.
            scene_source: Scene source identifier reported in results.
            planning_backend: Optional injected runtime backend.
            scene_provider: Optional injected planning-scene provider.

        Returns:
            None.

        Raises:
            ValueError: If planner_plugin or scene_source are empty.
        """
        if not planner_plugin:
            raise ValueError('planner_plugin must be non-empty')
        if not scene_source:
            raise ValueError('scene_source must be non-empty')
        self.planner_plugin = planner_plugin
        self.scene_source = scene_source
        self._planning_backend = planning_backend or self._fallback_backend
        self._scene_provider = scene_provider or self._fallback_scene_provider

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
            pose: Cartesian pose dictionary.
            frame: Pose reference frame.
            metadata: Optional tracing metadata.
            constraints: Optional planning constraints.

        Returns:
            PlanResult: Normalized planning response.

        Raises:
            ValueError: If pose/frame are invalid.
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
            stage: Stage request payload.
            metadata: Optional tracing metadata.

        Returns:
            PlanResult: Normalized planning response.

        Raises:
            ValueError: If stage is invalid.
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

    def _execute_request(self, request: PlanningRequest) -> PlanResult:
        """Execute a normalized request against the configured backend."""
        _ = self.query_scene_state()
        backend = self._planning_backend
        if backend is None:
            raise PlanningUnavailableError('planning backend unavailable')
        result = backend(request)
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
        )

    def _fallback_backend(self, request: PlanningRequest) -> PlanResult:
        """Produce a deterministic fallback plan result for tests and local tooling."""
        trajectory = {
            'requestKind': request.request_kind,
            'frame': request.frame,
            'target': dict(request.target),
            'waypoints': self._build_fallback_waypoints(request),
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
        )

    @staticmethod
    def _build_fallback_waypoints(request: PlanningRequest) -> list[dict[str, Any]]:
        """Build deterministic fallback waypoints from a normalized request."""
        if request.request_kind == 'named_pose':
            return [{'named_pose': request.target['named_pose']}]
        if request.request_kind in {'pose_goal', 'stage'}:
            return [dict(request.target)]
        return []
