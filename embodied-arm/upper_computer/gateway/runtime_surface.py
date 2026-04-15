from __future__ import annotations

"""Runtime surface helpers for execution backbone / release-gate projection.

This module centralizes operator-facing runtime surface summaries so gateway
state, REST, and frontend projections derive one coherent view of:
- the active execution backbone contract,
- validated-live release gates,
- promotion receipt state, and
- firmware semantic profile.
"""

from dataclasses import dataclass
from typing import Any

_BACKBONE_LABELS = {
    'protocol_simulator': 'Protocol Simulator',
    'dispatcher': 'Dispatcher Transport',
    'ros2_control': 'ros2_control Backbone',
    'local_preview': 'Local Preview Projection',
    'unknown': 'Unknown Backbone',
}

_EXECUTION_MODE_LABELS = {
    'protocol_simulator': 'simulated protocol',
    'authoritative_simulation': 'authoritative simulation',
    'ros2_control_candidate': 'ros2_control candidate',
    'ros2_control_live': 'ros2_control live',
}


@dataclass(frozen=True)
class RuntimeSurfaceSummary:
    """Normalized operator-facing runtime surface summary."""

    runtime_delivery_track: str
    execution_backbone: str
    execution_mode: str
    authoritative_transport: bool
    sequential_dispatch: bool
    requested_runtime_profile: str
    active_runtime_lane: str
    backbone_label: str
    firmware_profile: str
    firmware_message: str


def _bool(value: Any, default: bool = False) -> bool:
    return bool(value if value is not None else default)


def summarize_runtime_surface(
    *,
    runtime_tier: str,
    readiness: dict[str, Any],
    hardware: dict[str, Any],
    runtime_profile_details: dict[str, Any] | None,
    firmware_profiles: dict[str, Any] | None,
) -> dict[str, Any]:
    """Build one stable runtime-surface summary.

    Args:
        runtime_tier: Effective public runtime tier after fail-closed promotion.
        readiness: Current readiness snapshot.
        hardware: Current hardware projection.
        runtime_profile_details: Active runtime-profile detail payload loaded from
            runtime configuration. Missing data degrades to conservative defaults.
        firmware_profiles: Firmware semantic-profile catalog.

    Returns:
        dict[str, Any]: Serializable execution-backbone / firmware summary.

    Raises:
        Does not raise. Unknown or missing inputs fail closed to preview-shaped
        summaries so callers never need to guess runtime transport truth.

    Boundary behavior:
        - Local preview snapshots always project `local_preview`.
        - If no runtime profile is resolved, the helper falls back to the current
          public tier + hardware truth rather than inventing a validated-live lane.
    """
    runtime_profile_details = dict(runtime_profile_details or {})
    active_profile = runtime_profile_details.get('activeProfile') if isinstance(runtime_profile_details.get('activeProfile'), dict) else {}
    requested_runtime_profile = str(runtime_profile_details.get('requestedProfile', '') or '')
    active_runtime_lane = str(runtime_profile_details.get('activeRuntimeLane', '') or '')
    source = str(readiness.get('source', '') or '')
    simulated = bool(readiness.get('simulated', False) or hardware.get('simulated', False) or hardware.get('sourceStm32Simulated', False))

    execution_backbone = str(active_profile.get('execution_backbone', '') or '').strip()
    execution_mode = str(active_profile.get('hardware_execution_mode', '') or '').strip()
    runtime_delivery_track = str(active_profile.get('runtime_delivery_track', '') or '').strip() or ('official_active' if runtime_tier != 'validated_live' else 'experimental')
    sequential_dispatch = execution_backbone == 'ros2_control' or execution_mode in {'ros2_control_candidate', 'ros2_control_live'}
    authoritative_transport = execution_backbone in {'dispatcher', 'ros2_control'} and execution_mode not in {'protocol_simulator', ''}

    if source == 'gateway_dev_simulation':
        execution_backbone = 'local_preview'
        execution_mode = 'protocol_simulator'
        runtime_delivery_track = 'development_preview'
        authoritative_transport = False
        sequential_dispatch = False
    elif not execution_backbone:
        if runtime_tier == 'validated_live':
            execution_backbone = 'ros2_control'
            execution_mode = 'ros2_control_live'
            authoritative_transport = True
            sequential_dispatch = True
        elif runtime_tier == 'validated_sim':
            execution_backbone = 'dispatcher'
            execution_mode = 'authoritative_simulation'
            authoritative_transport = True
            sequential_dispatch = False
        else:
            execution_backbone = 'protocol_simulator'
            execution_mode = 'protocol_simulator'
            authoritative_transport = False
            sequential_dispatch = False

    backbone_label = _BACKBONE_LABELS.get(execution_backbone, _BACKBONE_LABELS['unknown'])
    execution_mode_label = _EXECUTION_MODE_LABELS.get(execution_mode, execution_mode or 'unknown')
    transport_mode = str(hardware.get('sourceStm32TransportMode', '') or '').strip()
    if transport_mode and transport_mode not in {'offline', 'unknown'}:
        backbone_label = f"{backbone_label} / {transport_mode}"

    firmware_profiles = dict(firmware_profiles or {})
    esp32 = firmware_profiles.get('esp32', {}) if isinstance(firmware_profiles.get('esp32'), dict) else {}
    profiles = esp32.get('profiles', {}) if isinstance(esp32.get('profiles'), dict) else {}
    firmware_profile = str(esp32.get('default_profile', 'preview_reserved') or 'preview_reserved')
    if active_runtime_lane:
        for name, payload in profiles.items():
            if isinstance(payload, dict) and str(payload.get('source_lane', '') or '') == active_runtime_lane:
                firmware_profile = str(name)
                break
    elif runtime_tier == 'validated_live' and 'validated_live_external_bridge' in profiles:
        firmware_profile = 'validated_live_external_bridge'
    elif runtime_tier == 'validated_sim' and 'validated_sim_synthetic' in profiles and simulated:
        firmware_profile = 'validated_sim_synthetic'
    firmware_payload = profiles.get(firmware_profile, {}) if isinstance(profiles.get(firmware_profile), dict) else {}
    firmware_message = str(firmware_payload.get('stream_message', '') or 'firmware semantic profile unavailable')

    return {
        'runtimeDeliveryTrack': runtime_delivery_track,
        'executionBackbone': execution_backbone,
        'executionMode': execution_mode,
        'executionModeLabel': execution_mode_label,
        'authoritativeTransport': authoritative_transport,
        'sequentialDispatch': sequential_dispatch,
        'requestedRuntimeProfile': requested_runtime_profile,
        'activeRuntimeLane': active_runtime_lane,
        'backboneLabel': backbone_label,
        'declaredByRuntimeProfile': bool(active_profile),
        'firmwareProfile': firmware_profile,
        'firmwareMessage': firmware_message,
    }
