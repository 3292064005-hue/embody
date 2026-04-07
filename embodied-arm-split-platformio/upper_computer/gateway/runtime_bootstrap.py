from __future__ import annotations

"""Gateway bootstrap and dev-simulation readiness helpers.

This module owns only gateway-local bootstrap profiles. Authoritative runtime
semantics remain defined in backend readiness contracts and projected through
generated mirrors in :mod:`gateway.generated.runtime_contract`.
"""

from typing import Any

from .generated.runtime_contract import ALL_READINESS_CHECKS, PUBLIC_COMMAND_NAMES, RUNTIME_HEALTH_REQUIRED
from .models import build_command_summary, bootstrap_command_policies, now_iso, simulated_local_only_command_policies


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
        'source': 'gateway_bootstrap',
        'authoritative': False,
        'simulated': False,
        'updatedAt': now_iso(),
    }


def simulated_local_only_snapshot(*, mode: str = 'simulated_local_only', controller_mode: str = 'maintenance', runtime_phase: str = 'idle', task_stage: str = 'created') -> dict[str, Any]:
    """Return the explicit dev-HMI-only simulated runtime snapshot.

    Args:
        mode: Public readiness mode token for the simulated snapshot.
        controller_mode: Controller mode projected to clients.
        runtime_phase: Runtime phase projected to clients.
        task_stage: Task stage projected to clients.

    Returns:
        dict[str, Any]: Serializable simulated-only readiness payload.

    Raises:
        Does not raise.

    Boundary behavior:
        Task execution remains denied even in simulated-local-only mode.
    """
    snapshot = default_readiness_snapshot()
    policies = simulated_local_only_command_policies()
    ready_detail = 'simulated_local_only'
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
    snapshot.update({
        'mode': mode,
        'controllerMode': controller_mode,
        'runtimePhase': runtime_phase,
        'taskStage': task_stage,
        'runtimeHealthy': True,
        'modeReady': False,
        'allReady': False,
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
