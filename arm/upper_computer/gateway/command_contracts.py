from __future__ import annotations

"""Helpers for consuming the authoritative command-plane and runtime-interface contracts.

This module centralizes command-plane metadata so gateway routers, transport
bridges, and receipt/audit emitters do not drift from the generated runtime
contract. It also resolves the runtime-interface registry used to gate public
command planes before transport dispatch.
"""

from typing import Any

from .generated.runtime_contract import COMMAND_PLANES, TASK_CAPABILITY_REGISTRY
from .security import ROLE_ORDER, normalize_role


USER_ROLE_ORDER = {role: order for role, order in ROLE_ORDER.items()}
_RUNTIME_INTERFACES = TASK_CAPABILITY_REGISTRY.get('runtime_interfaces', {}) if isinstance(TASK_CAPABILITY_REGISTRY, dict) else {}


def command_plane_contract(command_plane: str) -> dict[str, Any]:
    """Return the normalized authoritative contract for one command plane.

    Args:
        command_plane: Stable runtime command-plane key.

    Returns:
        dict[str, Any]: Normalized contract payload.

    Raises:
        KeyError: If the command plane is not declared in runtime authority.
    """
    payload = COMMAND_PLANES.get(str(command_plane))
    if not isinstance(payload, dict):
        raise KeyError(f'unknown command plane: {command_plane}')
    return dict(payload)



def allowed_roles_for_command_plane(command_plane: str) -> tuple[str, ...]:
    """Return the declared allowed roles for one command plane."""
    payload = command_plane_contract(command_plane)
    return tuple(normalize_role(role) if role in USER_ROLE_ORDER else str(role) for role in payload.get('allowed_roles', []))



def minimum_role_for_command_plane(command_plane: str) -> str | None:
    """Return the least-privileged interactive role allowed for a command plane.

    System-only planes, such as observability ingress, return ``None`` because
    they are not user-invoked command surfaces.
    """
    user_roles = [role for role in allowed_roles_for_command_plane(command_plane) if role in USER_ROLE_ORDER]
    if not user_roles:
        return None
    return min(user_roles, key=lambda role: USER_ROLE_ORDER[role])



def receipt_class_for_command_plane(command_plane: str) -> str:
    """Return the authoritative receipt class for one command plane."""
    payload = command_plane_contract(command_plane)
    return str(payload.get('receipt_class', 'observability_event') or 'observability_event')



def producer_for_command_plane(command_plane: str) -> str:
    """Return the authoritative producer identifier for one command plane."""
    payload = command_plane_contract(command_plane)
    return str(payload.get('producer', '') or '')



def dispatch_mode_for_command_plane(command_plane: str) -> str:
    """Return the authoritative dispatch mode for one command plane."""
    payload = command_plane_contract(command_plane)
    return str(payload.get('dispatch_mode', 'observability_only') or 'observability_only')



def runtime_interface_for_command_plane(command_plane: str) -> str:
    """Return the authoritative runtime-interface key bound to a command plane.

    Args:
        command_plane: Stable runtime command-plane key.

    Returns:
        str: Declared runtime-interface key.

    Raises:
        KeyError: If the command plane does not declare a runtime interface.
    """
    payload = command_plane_contract(command_plane)
    runtime_interface = str(payload.get('runtime_interface', '') or '')
    if not runtime_interface:
        raise KeyError(f'command plane {command_plane} does not declare a runtime interface')
    return runtime_interface



def runtime_interface_contract(runtime_interface: str) -> dict[str, Any]:
    """Return one normalized runtime-interface registry entry.

    Args:
        runtime_interface: Runtime-interface registry key.

    Returns:
        dict[str, Any]: Normalized runtime-interface payload.

    Raises:
        KeyError: If the runtime interface is not declared.
    """
    payload = _RUNTIME_INTERFACES.get(str(runtime_interface))
    if not isinstance(payload, dict):
        raise KeyError(f'unknown runtime interface: {runtime_interface}')
    return dict(payload)



def runtime_interface_state(runtime_interface: str) -> str:
    """Return the declared lifecycle state for one runtime interface."""
    payload = runtime_interface_contract(runtime_interface)
    return str(payload.get('state', 'reserved') or 'reserved')



def runtime_interface_active(runtime_interface: str) -> bool:
    """Return whether one runtime interface is currently active."""
    return runtime_interface_state(runtime_interface) == 'active'



def runtime_interface_active_for_command_plane(command_plane: str) -> bool:
    """Return whether the runtime interface bound to one command plane is active."""
    return runtime_interface_active(runtime_interface_for_command_plane(command_plane))



def execution_bound_for_command_plane(command_plane: str) -> bool:
    """Return whether one command plane is bound to an execution path."""
    return dispatch_mode_for_command_plane(command_plane) != 'observability_only'
