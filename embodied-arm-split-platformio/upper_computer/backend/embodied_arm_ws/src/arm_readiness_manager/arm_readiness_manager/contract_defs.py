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
    'task': ('ros2', 'task_orchestrator', 'motion_planner', 'motion_executor', 'hardware_bridge', 'camera_alive', 'perception_alive', 'target_available', 'calibration', 'profiles'),
    'manual': ('ros2', 'task_orchestrator', 'motion_planner', 'motion_executor', 'hardware_bridge'),
    'maintenance': ('ros2', 'task_orchestrator', 'motion_planner', 'motion_executor', 'hardware_bridge'),
    'safe_stop': ('ros2', 'hardware_bridge'),
    'fault': ('ros2', 'hardware_bridge'),
}

RUNTIME_HEALTH_REQUIRED = (
    'ros2',
    'task_orchestrator',
    'motion_planner',
    'motion_executor',
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
    return {
        'startTask': command_policy(False, 'task execution requires authoritative ROS runtime readiness'),
        'stopTask': command_policy(True, simulated_reason),
        'jog': command_policy(True, simulated_reason),
        'servoCartesian': command_policy(True, simulated_reason),
        'gripper': command_policy(True, simulated_reason),
        'home': command_policy(True, simulated_reason),
        'resetFault': command_policy(True, simulated_reason),
    }


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
    payload = checks.get(name, {})
    return bool(payload.get('effectiveOk', payload.get('ok', False)))


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
        Missing check entries are treated as not-ready. Unknown modes degrade to
        the stricter ``task`` requirements via :func:`required_checks_for_mode`.
    """
    task_required = [name for name in required_checks_for_mode('task') if name in checks]
    missing_task = [name for name in task_required if not _effective_check_ok(checks, name)]
    manual_required = [name for name in required_checks_for_mode('manual') if name in checks]
    missing_manual = [name for name in manual_required if not _effective_check_ok(checks, name)]

    def _missing_reason(missing: list[str], default_reason: str) -> str:
        if missing:
            return f"missing readiness: {', '.join(missing)}"
        return default_reason

    start_allowed = mode not in {'boot', 'safe_stop', 'fault', 'bootstrap'} and not missing_task
    manual_mode_enabled = mode in {'manual', 'maintenance', 'simulated_local_only'}
    manual_ready = manual_mode_enabled and not missing_manual
    hardware_fault = bool(checks.get('hardware_bridge', {}).get('detail') in {'fault', 'hardware_blocked', 'hardware_fault'})
    hardware_ready = _effective_check_ok(checks, 'hardware_bridge') or mode == 'simulated_local_only'
    home_allowed = mode not in {'safe_stop'} and hardware_ready and not hardware_fault
    if home_allowed:
        home_reason = 'ready'
    elif mode in {'safe_stop'} or hardware_fault:
        home_reason = 'home blocked by safe-stop or hardware fault'
    else:
        home_reason = 'missing readiness: hardware_bridge'

    return {
        'startTask': command_policy(start_allowed, 'ready' if start_allowed else _missing_reason(missing_task, f'mode {mode} does not allow task start')),
        'stopTask': command_policy(mode in {'task', 'manual', 'maintenance', 'safe_stop', 'fault', 'simulated_local_only'}, 'ready' if mode in {'task', 'manual', 'maintenance', 'safe_stop', 'fault', 'simulated_local_only'} else 'no active runtime command path'),
        'jog': command_policy(manual_ready, 'ready' if manual_ready else _missing_reason(missing_manual, 'manual operations require manual or maintenance mode')),
        'servoCartesian': command_policy(manual_ready, 'ready' if manual_ready else _missing_reason(missing_manual, 'manual operations require manual or maintenance mode')),
        'gripper': command_policy(manual_ready, 'ready' if manual_ready else _missing_reason(missing_manual, 'manual operations require manual or maintenance mode')),
        'home': command_policy(home_allowed, home_reason),
        'resetFault': command_policy(mode in {'fault', 'safe_stop'}, 'ready' if mode in {'fault', 'safe_stop'} else 'reset fault only valid in fault or safe-stop mode'),
    }


def build_readiness_layers(mode: str, checks: dict[str, dict[str, Any]]) -> tuple[bool, bool]:
    """Return runtime-health and mode-ready booleans from public check payloads."""
    runtime_healthy = all(_effective_check_ok(checks, name) for name in RUNTIME_HEALTH_REQUIRED)
    required = required_checks_for_mode(mode)
    mode_ready = bool(required) and all(_effective_check_ok(checks, name) for name in required)
    return runtime_healthy, mode_ready
