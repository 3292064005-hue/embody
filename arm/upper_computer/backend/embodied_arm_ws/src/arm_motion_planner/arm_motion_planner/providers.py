from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Protocol, runtime_checkable

from arm_backend_common import LocalRuntimeServiceClient
from arm_common import ServiceNames
from arm_grasp_planner import GraspPlanningService
from arm_scene_manager import SceneService

_RUNTIME_SCENE_SNAPSHOT = str(getattr(ServiceNames, 'RUNTIME_SCENE_SNAPSHOT'))
_RUNTIME_GRASP_PLAN = str(getattr(ServiceNames, 'RUNTIME_GRASP_PLAN'))


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


@dataclass(frozen=True)
class ProviderDescriptor:
    """Declarative registry entry for one planning provider surface."""

    name: str
    surface: str
    contract_version: int = 1
    state: str = 'active'
    description: str = ''


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


SceneProviderFactory = Callable[..., SceneSnapshotProvider]
GraspProviderFactory = Callable[..., GraspPlanProvider]

_SCENE_PROVIDER_REGISTRY: dict[str, tuple[ProviderDescriptor, SceneProviderFactory]] = {}
_GRASP_PROVIDER_REGISTRY: dict[str, tuple[ProviderDescriptor, GraspProviderFactory]] = {}


def register_scene_provider(
    name: str,
    factory: SceneProviderFactory,
    *,
    surface: str,
    contract_version: int = 1,
    state: str = 'active',
    description: str = '',
    replace: bool = False,
) -> None:
    normalized = str(name or '').strip()
    if not normalized:
        raise ValueError('scene provider name must be non-empty')
    if normalized in _SCENE_PROVIDER_REGISTRY and not replace:
        raise ValueError(f'scene provider already registered: {normalized}')
    _SCENE_PROVIDER_REGISTRY[normalized] = (
        ProviderDescriptor(
            name=normalized,
            surface=surface,
            contract_version=int(contract_version),
            state=str(state or 'active'),
            description=str(description or ''),
        ),
        factory,
    )


def register_grasp_provider(
    name: str,
    factory: GraspProviderFactory,
    *,
    surface: str,
    contract_version: int = 1,
    state: str = 'active',
    description: str = '',
    replace: bool = False,
) -> None:
    normalized = str(name or '').strip()
    if not normalized:
        raise ValueError('grasp provider name must be non-empty')
    if normalized in _GRASP_PROVIDER_REGISTRY and not replace:
        raise ValueError(f'grasp provider already registered: {normalized}')
    _GRASP_PROVIDER_REGISTRY[normalized] = (
        ProviderDescriptor(
            name=normalized,
            surface=surface,
            contract_version=int(contract_version),
            state=str(state or 'active'),
            description=str(description or ''),
        ),
        factory,
    )


def build_scene_provider(mode: str, **kwargs: Any) -> SceneSnapshotProvider:
    normalized = str(mode or 'embedded_core').strip().lower() or 'embedded_core'
    record = _SCENE_PROVIDER_REGISTRY.get(normalized)
    if record is None:
        raise ValueError(f'unsupported scene provider mode: {mode!r}')
    return record[1](**kwargs)


def build_grasp_provider(mode: str, **kwargs: Any) -> GraspPlanProvider:
    normalized = str(mode or 'embedded_core').strip().lower() or 'embedded_core'
    record = _GRASP_PROVIDER_REGISTRY.get(normalized)
    if record is None:
        raise ValueError(f'unsupported grasp provider mode: {mode!r}')
    return record[1](**kwargs)


def list_registered_provider_descriptors() -> dict[str, list[dict[str, object]]]:
    def _serialize(entries: dict[str, tuple[ProviderDescriptor, object]]) -> list[dict[str, object]]:
        payload: list[dict[str, object]] = []
        for key in sorted(entries):
            descriptor = entries[key][0]
            payload.append(
                {
                    'name': descriptor.name,
                    'surface': descriptor.surface,
                    'contractVersion': descriptor.contract_version,
                    'state': descriptor.state,
                    'description': descriptor.description,
                }
            )
        return payload

    return {
        'sceneProviders': _serialize(_SCENE_PROVIDER_REGISTRY),
        'graspProviders': _serialize(_GRASP_PROVIDER_REGISTRY),
    }


register_scene_provider(
    'embedded_core',
    lambda **kwargs: SceneManagerAdapter(service=kwargs.get('service')),
    surface='embedded_core_runtime',
    description='Direct in-process scene manager integration.',
)
register_scene_provider(
    'runtime_service',
    lambda **kwargs: SceneRuntimeServiceAdapter(
        client=kwargs.get('client'),
        authoritative=bool(kwargs.get('authoritative', True)),
        service_name=kwargs.get('service_name'),
    ),
    surface='runtime_service_boundary',
    description='Authoritative runtime-service scene snapshot provider.',
)
register_grasp_provider(
    'embedded_core',
    lambda **kwargs: GraspPlannerAdapter(service=kwargs.get('service')),
    surface='embedded_core_runtime',
    description='Direct in-process grasp planning integration.',
)
register_grasp_provider(
    'runtime_service',
    lambda **kwargs: GraspRuntimeServiceAdapter(
        client=kwargs.get('client'),
        authoritative=bool(kwargs.get('authoritative', True)),
        service_name=kwargs.get('service_name'),
    ),
    surface='runtime_service_boundary',
    description='Authoritative runtime-service grasp provider.',
)
