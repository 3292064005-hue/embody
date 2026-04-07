from __future__ import annotations

"""Pure helpers for lifecycle and bringup status payloads.

These helpers keep lifecycle failure semantics testable without a ROS runtime and
ensure JSON compatibility payloads stay aligned with typed shadow messages.
"""

from copy import deepcopy
from typing import Any


def bump_retry(retry_count: dict[str, int], node_name: str) -> int:
    retry_count[node_name] = int(retry_count.get(node_name, 0)) + 1
    return retry_count[node_name]


def mark_node_state(states: dict[str, str], retry_count: dict[str, int], node_name: str, state: str, *, increment_retry: bool = True) -> str:
    states[node_name] = str(state)
    if increment_retry:
        bump_retry(retry_count, node_name)
    return states[node_name]


def record_cleanup_failure(cleanup_failures: dict[str, str], retry_count: dict[str, int], node_name: str, error: Exception | str) -> None:
    cleanup_failures[node_name] = str(error)
    bump_retry(retry_count, node_name)


def build_managed_lifecycle_status_payload(
    *,
    stamp_monotonic: float,
    autostart_complete: bool,
    current_layer: str,
    blocking_node: str,
    retry_count: dict[str, int],
    terminal_fault_reason: str,
    layer_spec: list[tuple[str, list[str]]],
    states: dict[str, str],
    cleanup_failures: dict[str, str] | None = None,
) -> dict[str, Any]:
    cleanup_failures = cleanup_failures or {}
    iter_nodes = [name for _, members in layer_spec for name in members]
    return {
        'stampMonotonic': float(stamp_monotonic),
        'managedLifecycle': True,
        'autostartComplete': bool(autostart_complete),
        'currentLayer': str(current_layer),
        'blockingNode': str(blocking_node),
        'retryCount': deepcopy(retry_count),
        'terminalFaultReason': str(terminal_fault_reason),
        'cleanupFailures': deepcopy(cleanup_failures),
        'layers': [
            {
                'name': layer_name,
                'nodes': [{'name': name, 'state': states.get(name, 'unknown')} for name in members],
                'allActive': all(states.get(name) == 'active' for name in members),
            }
            for layer_name, members in layer_spec
        ],
        'nodes': [{'name': name, 'state': states.get(name, 'unknown')} for name in iter_nodes],
        'allActive': all(states.get(name) == 'active' for name in iter_nodes),
    }


def build_runtime_supervisor_status_payload(
    *,
    stamp_monotonic: float,
    required_nodes: list[str],
    hardware_seen: bool,
    system_seen: bool,
    calibration_loaded: bool,
    profiles_loaded: bool,
    readiness_streaming: bool,
    system_mode: int | None,
) -> dict[str, Any]:
    ready = bool(hardware_seen and system_seen and calibration_loaded and profiles_loaded and readiness_streaming)
    return {
        'stampMonotonic': float(stamp_monotonic),
        'managedLifecycle': False,
        'autostartComplete': ready,
        'currentLayer': 'runtime_supervision',
        'blockingNode': '' if ready else 'runtime_supervisor',
        'terminalFaultReason': '' if ready else 'incomplete_runtime_inputs',
        'requiredNodes': list(required_nodes),
        'phases': {
            'hardwareSeen': bool(hardware_seen),
            'systemSeen': bool(system_seen),
            'calibrationLoaded': bool(calibration_loaded),
            'profilesLoaded': bool(profiles_loaded),
            'readinessStreaming': bool(readiness_streaming),
        },
        'systemMode': system_mode,
        'ready': ready,
        'allActive': ready,
    }


__all__ = [
    'build_managed_lifecycle_status_payload',
    'build_runtime_supervisor_status_payload',
    'bump_retry',
    'mark_node_state',
    'record_cleanup_failure',
]
