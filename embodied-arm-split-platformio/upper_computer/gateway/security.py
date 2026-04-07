from __future__ import annotations

from dataclasses import dataclass
from typing import Any

ROLE_ORDER = {'viewer': 0, 'operator': 1, 'maintainer': 2}


@dataclass
class PolicyResult:
    """Authorization or safety policy decision."""

    allowed: bool
    reason: str = 'ok'


def normalize_role(value: str | None) -> str:
    """Normalize an operator role string to the supported role set."""
    value = (value or 'operator').strip().lower()
    return value if value in ROLE_ORDER else 'operator'


def require_role(current_role: str, minimum_role: str) -> PolicyResult:
    """Validate that the current role satisfies a minimum role."""
    current = normalize_role(current_role)
    minimum = normalize_role(minimum_role)
    if ROLE_ORDER[current] < ROLE_ORDER[minimum]:
        return PolicyResult(False, f'requires role {minimum}')
    return PolicyResult(True, 'ok')


def _command_policy(readiness: dict[str, Any], command_name: str) -> PolicyResult | None:
    """Read a command policy from the backend readiness snapshot if present."""
    payload = readiness.get('commandPolicies', {}).get(command_name)
    if not isinstance(payload, dict):
        return None
    return PolicyResult(bool(payload.get('allowed', False)), str(payload.get('reason', 'blocked by backend policy')))


def validate_mode_for_manual(operator_mode: str) -> PolicyResult:
    """Validate that manual operations are allowed for the current mode."""
    if operator_mode not in {'manual', 'maintenance'}:
        return PolicyResult(False, 'manual operations require manual or maintenance mode')
    return PolicyResult(True, 'ok')


def validate_gripper_command(operator_mode: str, readiness: dict[str, Any] | None = None) -> PolicyResult:
    """Validate a gripper command against backend policy and operator mode."""
    if readiness:
        policy = _command_policy(readiness, 'gripper')
        if policy and not policy.allowed:
            return policy
    return validate_mode_for_manual(operator_mode)


def validate_jog_command(joint_index: int, direction: int, step_deg: float, operator_mode: str, readiness: dict[str, Any] | None = None) -> PolicyResult:
    """Validate a joint jog command."""
    if readiness:
        policy = _command_policy(readiness, 'jog')
        if policy and not policy.allowed:
            return policy
    mode_check = validate_mode_for_manual(operator_mode)
    if not mode_check.allowed:
        return mode_check
    if joint_index < 0 or joint_index > 5:
        return PolicyResult(False, 'jointIndex out of range')
    if direction not in {-1, 1}:
        return PolicyResult(False, 'direction must be -1 or 1')
    if step_deg <= 0 or step_deg > 10:
        return PolicyResult(False, 'stepDeg must be in (0, 10]')
    return PolicyResult(True, 'ok')


def validate_servo_command(axis: str, delta: float, operator_mode: str, readiness: dict[str, Any] | None = None) -> PolicyResult:
    """Validate a cartesian servo command against backend policy and local bounds."""
    if readiness:
        policy = _command_policy(readiness, 'servoCartesian')
        if policy and not policy.allowed:
            return policy
    mode_check = validate_mode_for_manual(operator_mode)
    if not mode_check.allowed:
        return mode_check
    if axis not in {'x', 'y', 'z', 'rx', 'ry', 'rz'}:
        return PolicyResult(False, 'unsupported servo axis')
    if delta == 0 or abs(delta) > 0.1:
        return PolicyResult(False, 'delta must be within (-0.1, 0.1] and non-zero')
    return PolicyResult(True, 'ok')


def validate_start_task(readiness: dict[str, Any], operator_role: str) -> PolicyResult:
    """Validate task start against role and backend readiness policy."""
    role_check = require_role(operator_role, 'operator')
    if not role_check.allowed:
        return role_check
    policy = _command_policy(readiness, 'startTask')
    if policy is not None and not policy.allowed:
        return policy
    if not readiness.get('modeReady', readiness.get('allReady', False)):
        return PolicyResult(False, 'system not ready for tasks')
    return PolicyResult(True, 'ok')
