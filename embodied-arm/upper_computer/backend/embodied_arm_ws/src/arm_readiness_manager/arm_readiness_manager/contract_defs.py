from __future__ import annotations

"""Authoritative readiness-contract literals for the active runtime stack.

This module is intentionally limited to stable, serializable contract data and
pure helpers derived from that data. Runtime managers import these constants at
execution time, while repository tooling extracts them using AST parsing to
generate gateway/frontend mirrors. Keep this file free of ROS imports and any
environment-dependent side effects.
"""

from typing import Any, Iterable

DEFAULT_READINESS_CHECKS = (
    'ros2',
    'task_orchestrator',
    'motion_planner',
    'motion_executor',
    'scene_runtime_service',
    'grasp_runtime_service',
    'hardware_bridge',
    'camera',
    'camera_alive',
    'perception_alive',
    'target_available',
    'calibration',
    'profiles',
)

DEFAULT_STALE_AFTER = {
    'ros2': None,
    'task_orchestrator': 2.0,
    'motion_planner': 2.5,
    'motion_executor': 2.5,
    'scene_runtime_service': 2.5,
    'grasp_runtime_service': 2.5,
    'hardware_bridge': 1.5,
    'camera': 2.0,
    'camera_alive': 2.0,
    'perception_alive': 2.0,
    'target_available': 2.0,
    'calibration': None,
    'profiles': None,
}

READINESS_REQUIRED_BY_MODE = {
    'boot': ('ros2',),
    'idle': ('ros2', 'task_orchestrator', 'hardware_bridge', 'calibration', 'profiles'),
    'task': ('ros2', 'task_orchestrator', 'motion_planner', 'motion_executor', 'scene_runtime_service', 'grasp_runtime_service', 'hardware_bridge', 'camera_alive', 'perception_alive', 'target_available', 'calibration', 'profiles'),
    'manual': ('ros2', 'task_orchestrator', 'hardware_bridge'),
    'maintenance': ('ros2', 'task_orchestrator', 'hardware_bridge'),
    'safe_stop': ('ros2', 'hardware_bridge'),
    'fault': ('ros2', 'hardware_bridge'),
}

COMMAND_REQUIRED_BY_NAME = {
    'startTask': READINESS_REQUIRED_BY_MODE['task'],
    'stopTask': (),
    'jog': ('ros2', 'task_orchestrator', 'hardware_bridge'),
    'servoCartesian': ('ros2', 'task_orchestrator', 'hardware_bridge'),
    'gripper': ('ros2', 'task_orchestrator', 'hardware_bridge'),
    'home': ('ros2', 'hardware_bridge'),
    'resetFault': ('ros2', 'hardware_bridge'),
    'recover': ('ros2', 'task_orchestrator', 'hardware_bridge'),
}

COMMAND_ALLOWED_MODES = {
    'startTask': ('idle', 'task'),
    'stopTask': ('task', 'manual', 'maintenance', 'safe_stop', 'fault', 'simulated_local_only'),
    'jog': ('manual', 'maintenance', 'simulated_local_only'),
    'servoCartesian': ('manual', 'maintenance', 'simulated_local_only'),
    'gripper': ('manual', 'maintenance', 'simulated_local_only'),
    'home': ('idle', 'manual', 'maintenance', 'task', 'fault', 'simulated_local_only'),
    'resetFault': ('fault', 'safe_stop', 'simulated_local_only'),
    'recover': ('idle', 'maintenance', 'fault', 'safe_stop', 'simulated_local_only'),
}

RUNTIME_HEALTH_REQUIRED = (
    'ros2',
    'task_orchestrator',
    'motion_planner',
    'motion_executor',
    'scene_runtime_service',
    'grasp_runtime_service',
    'hardware_bridge',
    'calibration',
    'profiles',
)

PUBLIC_READINESS_FIELDS = (
    'runtimeHealthy',
    'modeReady',
    'allReady',
    'runtimeRequiredChecks',
    'runtimeMissingChecks',
    'requiredChecks',
    'missingChecks',
    'missingDetails',
    'checks',
    'commandPolicies',
    'commandSummary',
    'authoritative',
    'simulated',
    'runtimeTier',
    'productLine',
    'manualCommandLimits',
    'runtimeConfigVersion',
    'source',
    'updatedAt',
)

HARDWARE_AUTHORITY_FIELDS = (
    'sourceStm32Online',
    'sourceStm32Authoritative',
    'sourceStm32TransportMode',
    'sourceStm32Controllable',
    'sourceStm32Simulated',
    'sourceStm32SimulatedFallback',
)

SYSTEM_SEMANTIC_FIELDS = (
    'controllerMode',
    'runtimePhase',
    'taskStage',
)

COMPATIBILITY_ALIASES = {
    'mode': 'runtimePhase',
    'operatorMode': 'controllerMode',
    'currentStage': 'taskStage',
    'allReady': 'modeReady',
}

PUBLIC_COMMAND_NAMES = (
    'startTask',
    'stopTask',
    'jog',
    'servoCartesian',
    'gripper',
    'home',
    'resetFault',
    'recover',
)


def required_checks_for_mode(mode: str) -> tuple[str, ...]:
    """Return the authoritative readiness requirements for a public mode.

    Args:
        mode: Canonical readiness mode.

    Returns:
        Stable tuple of required readiness check names.

    Raises:
        Does not raise.

    Boundary behavior:
        Unknown modes degrade to the ``task`` profile so permissiveness is never
        widened by an unrecognized input token.
    """
    return READINESS_REQUIRED_BY_MODE.get(str(mode or '').strip().lower(), READINESS_REQUIRED_BY_MODE['task'])


def command_policy(allowed: bool, reason: str) -> dict[str, Any]:
    """Build a serializable command-policy record.

    Args:
        allowed: Whether the command is permitted.
        reason: Human-readable policy explanation.

    Returns:
        Plain dictionary safe for REST/WS transport.

    Raises:
        Does not raise.
    """
    return {'allowed': bool(allowed), 'reason': str(reason)}


def bootstrap_command_policies(reason: str = 'waiting for authoritative readiness snapshot') -> dict[str, dict[str, Any]]:
    """Return fail-closed bootstrap policies for all public commands."""
    return {name: command_policy(False, reason) for name in PUBLIC_COMMAND_NAMES}


def simulated_local_only_command_policies() -> dict[str, dict[str, Any]]:
    """Return explicit dev-only policies for the simulated-local-only profile."""
    simulated_reason = 'dev-hmi-mock simulated runtime'
    policies = {name: command_policy(False, simulated_reason) for name in PUBLIC_COMMAND_NAMES}
    policies.update({
        'startTask': command_policy(False, 'task execution requires authoritative ROS runtime readiness'),
        'stopTask': command_policy(True, simulated_reason),
        'jog': command_policy(True, simulated_reason),
        'servoCartesian': command_policy(True, simulated_reason),
        'gripper': command_policy(True, simulated_reason),
        'home': command_policy(True, simulated_reason),
        'resetFault': command_policy(True, simulated_reason),
        'recover': command_policy(True, simulated_reason),
    })
    return policies


def build_command_summary(command_policies: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Summarize command-policy readiness for operator-facing projections."""
    allowed = [name for name, payload in command_policies.items() if bool(payload.get('allowed'))]
    blocked = [name for name in command_policies if name not in allowed]
    return {
        'allowed': allowed,
        'blocked': blocked,
        'readyCount': len(allowed),
        'blockedCount': len(blocked),
    }


def _effective_check_ok(checks: dict[str, Any], name: str) -> bool:
    """Return the effective readiness flag for one check payload.

    Args:
        checks: Public readiness payload keyed by check name.
        name: Stable readiness check identifier.

    Returns:
        bool: ``True`` only when the check is present and effectively ready.

    Raises:
        Does not raise. Missing entries degrade to ``False``.
    """
    payload = checks.get(name, {})
    return bool(payload.get('effectiveOk', payload.get('ok', False)))


def _missing_required_checks(checks: dict[str, dict[str, Any]], names: Iterable[str]) -> list[str]:
    """Return missing readiness checks for a command or mode dependency set.

    Args:
        checks: Public readiness payload keyed by check name.
        names: Required readiness names to validate.

    Returns:
        list[str]: Missing or ineffective readiness checks in stable order.

    Raises:
        Does not raise. Missing keys are treated as not-ready.
    """
    return [name for name in names if not _effective_check_ok(checks, name)]


def _missing_reason(checks: dict[str, dict[str, Any]], missing: list[str], default_reason: str) -> str:
    """Render a stable command-policy deny reason.

    Args:
        checks: Public readiness payload keyed by check name.
        missing: Missing readiness check names.
        default_reason: Fallback message used when no checks are missing.

    Returns:
        str: Human-readable deny reason with per-check detail when available.

    Raises:
        Does not raise.
    """
    if not missing:
        return default_reason
    detailed: list[str] = []
    for name in missing:
        payload = checks.get(name, {})
        detail = str(payload.get('detail', '') or '').strip()
        detailed.append(f'{name}({detail})' if detail else name)
    return f"missing readiness: {', '.join(detailed)}"


def build_command_policies(mode: str, checks: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Derive authoritative command policies from readiness checks.

    Args:
        mode: Effective readiness mode.
        checks: Public readiness checks payload keyed by name.

    Returns:
        Mapping keyed by stable public command names.

    Raises:
        Does not raise.

    Boundary behavior:
        Missing check entries are treated as not-ready. Command policies are
        calculated per-command, so manual/maintenance controls are no longer
        implicitly blocked by planning-only dependencies.
    """
    normalized_mode = str(mode or '').strip().lower() or 'boot'
    start_missing = _missing_required_checks(checks, COMMAND_REQUIRED_BY_NAME['startTask'])
    manual_missing = _missing_required_checks(checks, COMMAND_REQUIRED_BY_NAME['jog'])
    home_missing = _missing_required_checks(checks, COMMAND_REQUIRED_BY_NAME['home'])
    reset_missing = _missing_required_checks(checks, COMMAND_REQUIRED_BY_NAME['resetFault'])
    recover_missing = _missing_required_checks(checks, COMMAND_REQUIRED_BY_NAME['recover'])

    start_allowed = normalized_mode in COMMAND_ALLOWED_MODES['startTask'] and not start_missing
    manual_ready = normalized_mode in COMMAND_ALLOWED_MODES['jog'] and not manual_missing
    stop_allowed = normalized_mode in COMMAND_ALLOWED_MODES['stopTask']
    hardware_fault = bool(checks.get('hardware_bridge', {}).get('detail') in {'fault', 'hardware_blocked', 'hardware_fault'})
    home_allowed = normalized_mode in COMMAND_ALLOWED_MODES['home'] and not home_missing and not hardware_fault
    reset_allowed = normalized_mode in COMMAND_ALLOWED_MODES['resetFault'] and not reset_missing
    recover_allowed = normalized_mode in COMMAND_ALLOWED_MODES['recover'] and not recover_missing

    if start_allowed:
        start_reason = 'ready'
    elif start_missing:
        start_reason = _missing_reason(checks, start_missing, 'task execution requires authoritative runtime lane')
    else:
        start_reason = f'mode {normalized_mode} does not allow task start'

    manual_reason = 'ready' if manual_ready else (_missing_reason(checks, manual_missing, 'manual operations require manual or maintenance mode') if manual_missing else 'manual operations require manual or maintenance mode')

    if home_allowed:
        home_reason = 'ready'
    elif hardware_fault:
        home_reason = 'home blocked by hardware fault'
    elif normalized_mode not in COMMAND_ALLOWED_MODES['home']:
        home_reason = 'home blocked by current runtime mode'
    else:
        home_reason = _missing_reason(checks, home_missing, 'missing readiness: hardware_bridge')

    if reset_allowed:
        reset_reason = 'ready'
    elif reset_missing:
        reset_reason = _missing_reason(checks, reset_missing, 'reset fault requires authoritative hardware bridge')
    else:
        reset_reason = 'reset fault only valid in fault or safe-stop mode'

    if recover_allowed:
        recover_reason = 'ready'
    elif recover_missing:
        recover_reason = _missing_reason(checks, recover_missing, 'recover requires authoritative runtime control path')
    else:
        recover_reason = 'recover only valid in idle / maintenance / fault / safe-stop mode'

    return {
        'startTask': command_policy(start_allowed, start_reason),
        'stopTask': command_policy(stop_allowed, 'ready' if stop_allowed else 'no active runtime command path'),
        'jog': command_policy(manual_ready, manual_reason),
        'servoCartesian': command_policy(manual_ready, manual_reason),
        'gripper': command_policy(manual_ready, manual_reason),
        'home': command_policy(home_allowed, home_reason),
        'resetFault': command_policy(reset_allowed, reset_reason),
        'recover': command_policy(recover_allowed, recover_reason),
    }


def build_readiness_layers(mode: str, checks: dict[str, dict[str, Any]]) -> tuple[bool, bool]:
    """Return runtime-health and mode-ready booleans from public check payloads."""
    runtime_healthy = all(_effective_check_ok(checks, name) for name in RUNTIME_HEALTH_REQUIRED)
    required = required_checks_for_mode(mode)
    mode_ready = bool(required) and all(_effective_check_ok(checks, name) for name in required)
    return runtime_healthy, mode_ready
