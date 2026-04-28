from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Protocol

from arm_backend_common.data_models import CalibrationProfile, TargetSnapshot, TaskContext
from arm_backend_common.stage_plan import StagePlan


@dataclass
class PlanningPipelineState:
    """Mutable state passed through planning pipeline hooks.

    Args:
        context: Active task context.
        target: Normalized target snapshot.
        calibration: Active calibration profile.
        place_pose: Normalized place pose resolved for the current request.
        metadata: Shared extension metadata for preprocessors and postprocessors.
    """

    context: TaskContext
    target: TargetSnapshot
    calibration: CalibrationProfile
    place_pose: dict[str, float]
    metadata: dict[str, object] = field(default_factory=dict)


class PlanningPreprocessor(Protocol):
    def __call__(self, state: PlanningPipelineState) -> PlanningPipelineState:
        ...


class PlanningPostprocessor(Protocol):
    def __call__(self, state: PlanningPipelineState, plan: list[StagePlan]) -> list[StagePlan]:
        ...


@dataclass(frozen=True)
class PlanningPluginDescriptor:
    """Machine-readable description of one pipeline extension.

    Attributes:
        name: Stable plugin identifier used by config, tests and node parameters.
        stage: Pipeline stage: ``preprocessor`` or ``postprocessor``.
        contract_version: Extension contract version.
        state: Deployment state such as ``active`` or ``experimental``.
        description: Human-readable intent of the plugin.
    """

    name: str
    stage: str
    contract_version: int = 1
    state: str = 'active'
    description: str = ''


_PREPROCESSOR_REGISTRY: dict[str, tuple[PlanningPluginDescriptor, PlanningPreprocessor]] = {}
_POSTPROCESSOR_REGISTRY: dict[str, tuple[PlanningPluginDescriptor, PlanningPostprocessor]] = {}


def register_preprocessor_plugin(
    name: str,
    plugin: PlanningPreprocessor,
    *,
    contract_version: int = 1,
    state: str = 'active',
    description: str = '',
    replace: bool = False,
) -> None:
    """Register one named planning preprocessor plugin.

    Raises:
        ValueError: If the plugin name is empty or already registered and ``replace``
            is not enabled.
    """
    normalized = str(name or '').strip()
    if not normalized:
        raise ValueError('preprocessor plugin name must be non-empty')
    if normalized in _PREPROCESSOR_REGISTRY and not replace:
        raise ValueError(f'preprocessor plugin already registered: {normalized}')
    _PREPROCESSOR_REGISTRY[normalized] = (
        PlanningPluginDescriptor(
            name=normalized,
            stage='preprocessor',
            contract_version=int(contract_version),
            state=str(state or 'active'),
            description=str(description or ''),
        ),
        plugin,
    )


def register_postprocessor_plugin(
    name: str,
    plugin: PlanningPostprocessor,
    *,
    contract_version: int = 1,
    state: str = 'active',
    description: str = '',
    replace: bool = False,
) -> None:
    """Register one named planning postprocessor plugin.

    Raises:
        ValueError: If the plugin name is empty or already registered and ``replace``
            is not enabled.
    """
    normalized = str(name or '').strip()
    if not normalized:
        raise ValueError('postprocessor plugin name must be non-empty')
    if normalized in _POSTPROCESSOR_REGISTRY and not replace:
        raise ValueError(f'postprocessor plugin already registered: {normalized}')
    _POSTPROCESSOR_REGISTRY[normalized] = (
        PlanningPluginDescriptor(
            name=normalized,
            stage='postprocessor',
            contract_version=int(contract_version),
            state=str(state or 'active'),
            description=str(description or ''),
        ),
        plugin,
    )


def resolve_preprocessor_plugins(names: tuple[str, ...] | list[str] | None) -> tuple[PlanningPreprocessor, ...]:
    """Resolve one ordered list of registered preprocessors.

    Raises:
        ValueError: If any requested plugin is unknown.
    """
    resolved: list[PlanningPreprocessor] = []
    for raw_name in tuple(names or ()):
        normalized = str(raw_name or '').strip()
        if not normalized:
            continue
        record = _PREPROCESSOR_REGISTRY.get(normalized)
        if record is None:
            raise ValueError(f'unknown planning preprocessor plugin: {normalized}')
        resolved.append(record[1])
    return tuple(resolved)


def resolve_postprocessor_plugins(names: tuple[str, ...] | list[str] | None) -> tuple[PlanningPostprocessor, ...]:
    """Resolve one ordered list of registered postprocessors.

    Raises:
        ValueError: If any requested plugin is unknown.
    """
    resolved: list[PlanningPostprocessor] = []
    for raw_name in tuple(names or ()):
        normalized = str(raw_name or '').strip()
        if not normalized:
            continue
        record = _POSTPROCESSOR_REGISTRY.get(normalized)
        if record is None:
            raise ValueError(f'unknown planning postprocessor plugin: {normalized}')
        resolved.append(record[1])
    return tuple(resolved)


def list_registered_pipeline_plugins() -> dict[str, list[dict[str, object]]]:
    """Return one serializable snapshot of registered planning extensions."""
    def _serialize(entries: dict[str, tuple[PlanningPluginDescriptor, object]]) -> list[dict[str, object]]:
        payload: list[dict[str, object]] = []
        for key in sorted(entries):
            descriptor = entries[key][0]
            payload.append(
                {
                    'name': descriptor.name,
                    'stage': descriptor.stage,
                    'contractVersion': descriptor.contract_version,
                    'state': descriptor.state,
                    'description': descriptor.description,
                }
            )
        return payload

    return {
        'preprocessors': _serialize(_PREPROCESSOR_REGISTRY),
        'postprocessors': _serialize(_POSTPROCESSOR_REGISTRY),
    }


@dataclass
class PlanningPipeline:
    """Composable planning pipeline used by :class:`MotionPlanner`.

    The pipeline standardizes extension points so preprocessors and
    postprocessors can be attached through one registry-backed contract instead
    of ad-hoc call chains.
    """

    preprocessors: tuple[PlanningPreprocessor, ...] = ()
    postprocessors: tuple[PlanningPostprocessor, ...] = ()

    def run_preprocessors(self, state: PlanningPipelineState) -> PlanningPipelineState:
        for hook in self.preprocessors:
            state = hook(state)
        return state

    def run_postprocessors(self, state: PlanningPipelineState, plan: list[StagePlan]) -> list[StagePlan]:
        for hook in self.postprocessors:
            plan = hook(state, plan)
        return plan


# Built-in no-op extensions establish a stable plugin contract even when callers
# do not opt into richer pipeline customization.
def _stamp_pipeline_contract(state: PlanningPipelineState) -> PlanningPipelineState:
    state.metadata.setdefault('pipelineContractVersion', 1)
    return state


def _echo_pipeline_contract(state: PlanningPipelineState, plan: list[StagePlan]) -> list[StagePlan]:
    if state.metadata:
        for stage in plan:
            if isinstance(stage.payload, dict):
                stage.payload.setdefault('planningPipelineMetadata', dict(state.metadata))
    return plan


register_preprocessor_plugin(
    'stamp_pipeline_contract',
    _stamp_pipeline_contract,
    description='Annotate pipeline metadata with the active contract version.',
)
register_postprocessor_plugin(
    'echo_pipeline_contract',
    _echo_pipeline_contract,
    description='Propagate pipeline metadata into serialized stage payloads.',
)
