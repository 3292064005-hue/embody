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


def summarize_node_failures(layer_spec: list[tuple[str, list[str]]], states: dict[str, str]) -> list[dict[str, str]]:
    """Return all managed nodes that are not currently active.

    Args:
        layer_spec: Ordered layer-to-node membership mapping.
        states: Latest node state labels keyed by node name.

    Returns:
        list[dict[str, str]]: One entry per non-active node preserving layer and
            reported state.

    Raises:
        Does not raise.
    """
    failures: list[dict[str, str]] = []
    for layer_name, members in layer_spec:
        for name in members:
            state = str(states.get(name, 'unknown') or 'unknown')
            if state != 'active':
                failures.append({'layer': layer_name, 'name': name, 'state': state})
    return failures


def phase_health_entry(*, seen: bool, fresh: bool, age_sec: float | None) -> dict[str, Any]:
    """Build one runtime-input health entry with deterministic numeric coercion."""
    return {
        'seen': bool(seen),
        'fresh': bool(fresh),
        'ageSec': None if age_sec is None else float(age_sec),
    }


def first_failed_phase(phase_health: dict[str, dict[str, Any]]) -> tuple[str, str]:
    """Return the first missing or stale phase token and its fault reason."""
    for name, entry in phase_health.items():
        if not bool(entry.get('seen', False)):
            return name, f'missing_{name}'
        if not bool(entry.get('fresh', False)):
            return name, f'stale_{name}'
    return '', ''


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
    supervision_active: bool = True,
) -> dict[str, Any]:
    cleanup_failures = cleanup_failures or {}
    iter_nodes = [name for _, members in layer_spec for name in members]
    node_failures = summarize_node_failures(layer_spec, states)
    return {
        'stampMonotonic': float(stamp_monotonic),
        'managedLifecycle': True,
        'autostartComplete': bool(autostart_complete),
        'currentLayer': str(current_layer),
        'blockingNode': str(blocking_node),
        'retryCount': deepcopy(retry_count),
        'terminalFaultReason': str(terminal_fault_reason),
        'cleanupFailures': deepcopy(cleanup_failures),
        'supervisionActive': bool(supervision_active),
        'nodeFailures': node_failures,
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
    hardware_fresh: bool | None = None,
    system_fresh: bool | None = None,
    calibration_fresh: bool | None = None,
    profiles_fresh: bool | None = None,
    readiness_fresh: bool | None = None,
    hardware_age_sec: float | None = None,
    system_age_sec: float | None = None,
    calibration_age_sec: float | None = None,
    profiles_age_sec: float | None = None,
    readiness_age_sec: float | None = None,
    stale_after_sec: float | None = None,
) -> dict[str, Any]:
    phase_health = {
        'hardware': phase_health_entry(seen=hardware_seen, fresh=hardware_seen if hardware_fresh is None else hardware_fresh, age_sec=hardware_age_sec),
        'system': phase_health_entry(seen=system_seen, fresh=system_seen if system_fresh is None else system_fresh, age_sec=system_age_sec),
        'calibration': phase_health_entry(seen=calibration_loaded, fresh=calibration_loaded if calibration_fresh is None else calibration_fresh, age_sec=calibration_age_sec),
        'profiles': phase_health_entry(seen=profiles_loaded, fresh=profiles_loaded if profiles_fresh is None else profiles_fresh, age_sec=profiles_age_sec),
        'readiness': phase_health_entry(seen=readiness_streaming, fresh=readiness_streaming if readiness_fresh is None else readiness_fresh, age_sec=readiness_age_sec),
    }
    ready = all(bool(entry['seen']) and bool(entry['fresh']) for entry in phase_health.values())
    failed_phase, fault_reason = first_failed_phase(phase_health)
    return {
        'stampMonotonic': float(stamp_monotonic),
        'managedLifecycle': False,
        'autostartComplete': ready,
        'currentLayer': 'runtime_supervision',
        'blockingNode': '' if ready else f'runtime_supervisor:{failed_phase or "unknown"}',
        'terminalFaultReason': '' if ready else (fault_reason or 'incomplete_runtime_inputs'),
        'requiredNodes': list(required_nodes),
        'phases': {
            'hardwareSeen': bool(hardware_seen),
            'systemSeen': bool(system_seen),
            'calibrationLoaded': bool(calibration_loaded),
            'profilesLoaded': bool(profiles_loaded),
            'readinessStreaming': bool(readiness_streaming),
        },
        'phaseHealth': phase_health,
        'staleAfterSec': None if stale_after_sec is None else float(stale_after_sec),
        'systemMode': system_mode,
        'ready': ready,
        'allActive': ready,
    }


__all__ = [
    'build_managed_lifecycle_status_payload',
    'build_runtime_supervisor_status_payload',
    'bump_retry',
    'first_failed_phase',
    'mark_node_state',
    'phase_health_entry',
    'record_cleanup_failure',
    'summarize_node_failures',
]
