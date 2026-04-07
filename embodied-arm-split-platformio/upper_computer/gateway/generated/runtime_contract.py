from __future__ import annotations

"""Generated gateway runtime-contract mirror. Do not edit manually."""

from typing import Any

PUBLIC_READINESS_FIELDS = ('runtimeHealthy', 'modeReady', 'allReady', 'runtimeRequiredChecks', 'runtimeMissingChecks', 'requiredChecks', 'missingChecks', 'missingDetails', 'checks', 'commandPolicies', 'commandSummary', 'authoritative', 'simulated', 'source', 'updatedAt')
RUNTIME_HEALTH_REQUIRED = ('ros2', 'task_orchestrator', 'motion_planner', 'motion_executor', 'hardware_bridge', 'calibration', 'profiles')
READINESS_REQUIRED_BY_MODE = {'boot': ('ros2',), 'idle': ('ros2', 'task_orchestrator', 'hardware_bridge', 'calibration', 'profiles'), 'task': ('ros2', 'task_orchestrator', 'motion_planner', 'motion_executor', 'hardware_bridge', 'camera_alive', 'perception_alive', 'target_available', 'calibration', 'profiles'), 'manual': ('ros2', 'task_orchestrator', 'motion_planner', 'motion_executor', 'hardware_bridge'), 'maintenance': ('ros2', 'task_orchestrator', 'motion_planner', 'motion_executor', 'hardware_bridge'), 'safe_stop': ('ros2', 'hardware_bridge'), 'fault': ('ros2', 'hardware_bridge')}
ALL_READINESS_CHECKS = ('ros2', 'task_orchestrator', 'motion_planner', 'motion_executor', 'hardware_bridge', 'calibration', 'profiles', 'camera_alive', 'perception_alive', 'target_available')
PUBLIC_COMMAND_NAMES = ('startTask', 'stopTask', 'jog', 'servoCartesian', 'gripper', 'home', 'resetFault')
HARDWARE_AUTHORITY_FIELDS = ('sourceStm32Online', 'sourceStm32Authoritative', 'sourceStm32TransportMode', 'sourceStm32Controllable', 'sourceStm32Simulated', 'sourceStm32SimulatedFallback')
SYSTEM_SEMANTIC_FIELDS = ('controllerMode', 'runtimePhase', 'taskStage')
COMPATIBILITY_ALIASES = {'mode': 'runtimePhase', 'operatorMode': 'controllerMode', 'currentStage': 'taskStage', 'allReady': 'modeReady'}

def required_checks_for_mode(mode: str) -> tuple[str, ...]:
    normalized = str(mode or "").strip().lower()
    return READINESS_REQUIRED_BY_MODE.get(normalized, READINESS_REQUIRED_BY_MODE['task'])

def _command_policy(allowed: bool, reason: str) -> dict[str, Any]:
    return {'allowed': bool(allowed), 'reason': str(reason)}

def build_command_policies(mode: str, checks: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    task_required = [name for name in required_checks_for_mode('task') if name in checks]
    missing_task = [name for name in task_required if not bool(checks.get(name, {}).get('effectiveOk', checks.get(name, {}).get('ok')))]
    manual_required = [name for name in required_checks_for_mode('manual') if name in checks]
    missing_manual = [name for name in manual_required if not bool(checks.get(name, {}).get('effectiveOk', checks.get(name, {}).get('ok')))]

    def _missing_reason(missing: list[str], default_reason: str) -> str:
        return 'missing readiness: ' + ', '.join(missing) if missing else default_reason

    start_allowed = mode not in {'boot', 'safe_stop', 'fault'} and not missing_task
    manual_mode_enabled = mode in {'manual', 'maintenance'}
    manual_ready = manual_mode_enabled and not missing_manual
    hardware_fault = bool(checks.get('hardware_bridge', {}).get('detail') in {'fault', 'hardware_blocked'})
    return {
        'startTask': _command_policy(start_allowed, 'ready' if start_allowed else _missing_reason(missing_task, f'mode {mode} does not allow task start')),
        'stopTask': _command_policy(mode in {'task', 'manual', 'maintenance', 'safe_stop', 'fault'}, 'ready' if mode in {'task', 'manual', 'maintenance', 'safe_stop', 'fault'} else 'no active runtime command path'),
        'jog': _command_policy(manual_ready, 'ready' if manual_ready else _missing_reason(missing_manual, 'manual operations require manual or maintenance mode')),
        'servoCartesian': _command_policy(manual_ready, 'ready' if manual_ready else _missing_reason(missing_manual, 'manual operations require manual or maintenance mode')),
        'gripper': _command_policy(manual_ready, 'ready' if manual_ready else _missing_reason(missing_manual, 'manual operations require manual or maintenance mode')),
        'home': _command_policy(mode not in {'safe_stop'} and not hardware_fault, 'ready' if mode not in {'safe_stop'} and not hardware_fault else 'home blocked by safe-stop or hardware fault'),
        'resetFault': _command_policy(mode in {'fault', 'safe_stop'}, 'ready' if mode in {'fault', 'safe_stop'} else 'reset fault only valid in fault or safe-stop mode'),
    }

def build_readiness_layers(mode: str, checks: dict[str, dict[str, Any]]) -> tuple[bool, bool]:
    runtime_healthy = all(bool(checks.get(name, {}).get('effectiveOk', checks.get(name, {}).get('ok', False))) for name in RUNTIME_HEALTH_REQUIRED)
    required = required_checks_for_mode(mode)
    mode_ready = bool(required) and all(bool(checks.get(name, {}).get('effectiveOk', checks.get(name, {}).get('ok', False))) for name in required)
    return runtime_healthy, mode_ready
