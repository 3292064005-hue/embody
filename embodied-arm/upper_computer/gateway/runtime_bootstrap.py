from __future__ import annotations

"""Gateway bootstrap and dev-simulation readiness helpers.

This module owns only gateway-local bootstrap profiles. Authoritative runtime
semantics remain defined in backend readiness contracts and projected through
generated mirrors in :mod:`gateway.generated.runtime_contract`.
"""

from typing import Any

from .generated.runtime_contract import ALL_READINESS_CHECKS, PUBLIC_COMMAND_NAMES, RUNTIME_HEALTH_REQUIRED
from .models import build_command_policies, build_command_summary, bootstrap_command_policies, now_iso


def default_readiness_snapshot() -> dict[str, Any]:
    """Return the fail-closed gateway bootstrap readiness snapshot.

    Returns:
        dict[str, Any]: Serializable bootstrap readiness payload.

    Raises:
        Does not raise.

    Boundary behavior:
        The payload is deliberately non-authoritative until the gateway receives
        an explicit backend snapshot or an explicit dev-only simulated profile.
    """
    checks = {name: {'ok': False, 'detail': 'waiting_backend_snapshot'} for name in ALL_READINESS_CHECKS}
    reason = 'waiting for authoritative readiness snapshot'
    policies = bootstrap_command_policies(reason)
    return {
        'mode': 'bootstrap',
        'controllerMode': 'idle',
        'runtimePhase': 'boot',
        'taskStage': 'created',
        'runtimeHealthy': False,
        'modeReady': False,
        'allReady': False,
        'requiredChecks': [],
        'runtimeRequiredChecks': list(RUNTIME_HEALTH_REQUIRED),
        'missingChecks': [],
        'runtimeMissingChecks': list(RUNTIME_HEALTH_REQUIRED),
        'missingDetails': [],
        'checks': checks,
        'commandPolicies': policies,
        'commandSummary': build_command_summary(policies),
        'runtimeDeliveryTrack': 'bootstrap',
        'executionBackbone': 'protocol_simulator',
        'executionBackboneSummary': {
            'runtimeDeliveryTrack': 'bootstrap',
            'executionBackbone': 'protocol_simulator',
            'executionMode': 'protocol_simulator',
            'executionModeLabel': 'simulated protocol',
            'authoritativeTransport': False,
            'sequentialDispatch': False,
            'requestedRuntimeProfile': '',
            'activeRuntimeLane': '',
            'backboneLabel': 'Protocol Simulator',
            'declaredByRuntimeProfile': False,
            'firmwareProfile': 'preview_reserved',
            'firmwareMessage': 'bootstrap readiness snapshot',
        },
        'promotionReceipts': {},
        'releaseGates': {},
        'firmwareSemanticProfile': 'preview_reserved',
        'firmwareSemanticMessage': 'bootstrap readiness snapshot',
        'source': 'gateway_bootstrap',
        'authoritative': False,
        'simulated': False,
        'updatedAt': now_iso(),
    }


def local_preview_snapshot(*, mode: str = 'maintenance', controller_mode: str = 'maintenance', runtime_phase: str = 'idle', task_stage: str = 'created') -> dict[str, Any]:
    """Return the explicit gateway-local preview snapshot.

    Args:
        mode: Canonical readiness mode projected to clients. Defaults to
            ``maintenance`` so the local preview no longer invents a synthetic
            readiness mode outside the authoritative contract taxonomy.
        controller_mode: Controller mode projected to clients.
        runtime_phase: Runtime phase projected to clients.
        task_stage: Task stage projected to clients.

    Returns:
        dict[str, Any]: Serializable local-preview readiness payload.

    Raises:
        Does not raise.

    Boundary behavior:
        The snapshot remains non-authoritative and keeps task execution denied.
        Manual / maintenance commands reuse the canonical contract rules instead
        of a gateway-only pseudo mode.
    """
    snapshot = default_readiness_snapshot()
    ready_detail = 'gateway_local_preview'
    checks = dict(snapshot.get('checks', {}))
    checks.update({
        'ros2': {'ok': True, 'effectiveOk': True, 'detail': ready_detail},
        'task_orchestrator': {'ok': True, 'effectiveOk': True, 'detail': ready_detail},
        'motion_planner': {'ok': True, 'effectiveOk': True, 'detail': ready_detail},
        'motion_executor': {'ok': True, 'effectiveOk': True, 'detail': ready_detail},
        'hardware_bridge': {'ok': True, 'effectiveOk': True, 'detail': ready_detail},
        'calibration': {'ok': True, 'effectiveOk': True, 'detail': 'profile_loaded'},
        'profiles': {'ok': True, 'effectiveOk': True, 'detail': 'profiles_loaded'},
    })
    policies = build_command_policies(mode, checks)
    snapshot.update({
        'mode': mode,
        'controllerMode': controller_mode,
        'runtimePhase': runtime_phase,
        'taskStage': task_stage,
        'runtimeHealthy': True,
        'modeReady': True,
        'allReady': True,
        'requiredChecks': [],
        'missingChecks': [],
        'runtimeMissingChecks': [],
        'missingDetails': [],
        'checks': checks,
        'commandPolicies': policies,
        'commandSummary': build_command_summary(policies),
        'source': 'gateway_dev_simulation',
        'authoritative': False,
        'simulated': True,
        'updatedAt': now_iso(),
    })
    return snapshot
