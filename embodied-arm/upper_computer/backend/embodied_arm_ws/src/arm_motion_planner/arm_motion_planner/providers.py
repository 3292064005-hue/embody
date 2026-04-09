from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from arm_backend_common import LocalRuntimeServiceClient
from arm_common import ServiceNames
from arm_grasp_planner import GraspPlanningService
from arm_scene_manager import SceneService

_RUNTIME_SCENE_SNAPSHOT = (
    ServiceNames.RUNTIME_SCENE_SNAPSHOT
)
_RUNTIME_GRASP_PLAN = (
    ServiceNames.RUNTIME_GRASP_PLAN
)


@runtime_checkable
class SceneSnapshotProvider(Protocol):
    """Port used by :class:`MotionPlanner` to obtain scene snapshots."""

    provider_mode: str
    authoritative: bool

    def sync_scene(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Apply a scene-sync payload and return the updated snapshot."""


@runtime_checkable
class GraspPlanProvider(Protocol):
    """Port used by :class:`MotionPlanner` to obtain grasp plans."""

    provider_mode: str
    authoritative: bool

    def plan(
        self,
        target: dict[str, Any],
        place_zone: dict[str, Any] | None = None,
        *,
        failed_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        """Return a serialized grasp plan for a target and place zone."""


class SceneManagerAdapter:
    """Default adapter exposing the pure :class:`SceneService` scene port."""

    provider_mode = 'embedded_core'
    authoritative = False

    def __init__(self, service: SceneService | None = None) -> None:
        self._service = service or SceneService()

    def sync_scene(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._service.sync_scene(payload)


class GraspPlannerAdapter:
    """Default adapter exposing the pure :class:`GraspPlanningService` port."""

    provider_mode = 'embedded_core'
    authoritative = False

    def __init__(self, service: GraspPlanningService | None = None) -> None:
        self._service = service or GraspPlanningService()

    def plan(
        self,
        target: dict[str, Any],
        place_zone: dict[str, Any] | None = None,
        *,
        failed_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        return self._service.plan(target, place_zone, failed_ids=failed_ids)


class SceneRuntimeServiceAdapter:
    """Planner adapter that consumes the scene runtime-service boundary."""

    provider_mode = 'runtime_service'

    def __init__(
        self,
        client: Any | None = None,
        *,
        authoritative: bool = True,
        service_name: str | None = None,
    ) -> None:
        self.authoritative = bool(authoritative)
        self._service_name = str(service_name or _RUNTIME_SCENE_SNAPSHOT)
        self._client = client or LocalRuntimeServiceClient(self._service_name)

    def sync_scene(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(payload, dict):
            raise ValueError('payload must be a dictionary')
        return self._client.call({'scene': dict(payload)})


class GraspRuntimeServiceAdapter:
    """Planner adapter that consumes the grasp runtime-service boundary."""

    provider_mode = 'runtime_service'

    def __init__(
        self,
        client: Any | None = None,
        *,
        authoritative: bool = True,
        service_name: str | None = None,
    ) -> None:
        self.authoritative = bool(authoritative)
        self._service_name = str(service_name or _RUNTIME_GRASP_PLAN)
        self._client = client or LocalRuntimeServiceClient(self._service_name)

    def plan(
        self,
        target: dict[str, Any],
        place_zone: dict[str, Any] | None = None,
        *,
        failed_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        if not isinstance(target, dict) or not target:
            raise ValueError('target must be a non-empty dictionary')
        if place_zone is not None and not isinstance(place_zone, dict):
            raise ValueError('place_zone must be a dictionary when provided')
        if failed_ids is not None and not isinstance(failed_ids, list):
            raise ValueError('failed_ids must be a list when provided')
        return self._client.call({'target': dict(target), 'place': dict(place_zone or {}), 'failedIds': list(failed_ids or [])})
