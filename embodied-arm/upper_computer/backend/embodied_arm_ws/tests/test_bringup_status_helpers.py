from __future__ import annotations

from arm_lifecycle_manager.bringup_status import (
    build_managed_lifecycle_status_payload,
    build_runtime_supervisor_status_payload,
    first_failed_phase,
    mark_node_state,
    record_cleanup_failure,
    summarize_node_failures,
)


def test_build_managed_lifecycle_status_payload_preserves_failure_matrix() -> None:
    states = {'node_a': 'active', 'node_b': 'timeout'}
    retry_count = {'node_b': 2}
    cleanup_failures = {'node_b': 'destroy_client failed'}
    payload = build_managed_lifecycle_status_payload(
        stamp_monotonic=1.25,
        autostart_complete=False,
        current_layer='motion',
        blocking_node='node_b',
        retry_count=retry_count,
        terminal_fault_reason='activate failed in layer motion',
        layer_spec=[('motion', ['node_a', 'node_b'])],
        states=states,
        cleanup_failures=cleanup_failures,
    )
    assert payload['managedLifecycle'] is True
    assert payload['currentLayer'] == 'motion'
    assert payload['blockingNode'] == 'node_b'
    assert payload['layers'][0]['allActive'] is False
    assert payload['cleanupFailures']['node_b'] == 'destroy_client failed'


def test_runtime_supervisor_payload_exposes_phase_gate() -> None:
    payload = build_runtime_supervisor_status_payload(
        stamp_monotonic=2.5,
        required_nodes=['a', 'b'],
        hardware_seen=True,
        system_seen=True,
        calibration_loaded=False,
        profiles_loaded=True,
        readiness_streaming=True,
        system_mode=3,
    )
    assert payload['managedLifecycle'] is False
    assert payload['ready'] is False
    assert payload['blockingNode'] == 'runtime_supervisor:calibration'
    assert payload['terminalFaultReason'] == 'missing_calibration'
    assert payload['phases']['calibrationLoaded'] is False


def test_failure_helpers_increment_retry_and_track_cleanup() -> None:
    states: dict[str, str] = {}
    retry_count: dict[str, int] = {}
    cleanup_failures: dict[str, str] = {}
    mark_node_state(states, retry_count, 'node_a', 'service_unavailable')
    record_cleanup_failure(cleanup_failures, retry_count, 'node_a', RuntimeError('destroy_client failed'))
    assert states['node_a'] == 'service_unavailable'
    assert retry_count['node_a'] == 2
    assert cleanup_failures['node_a'] == 'destroy_client failed'


def test_runtime_supervisor_payload_tracks_missing_vs_stale_inputs() -> None:
    payload = build_runtime_supervisor_status_payload(
        stamp_monotonic=5.0,
        required_nodes=['a', 'b'],
        hardware_seen=True,
        system_seen=True,
        calibration_loaded=True,
        profiles_loaded=True,
        readiness_streaming=True,
        system_mode=1,
        hardware_fresh=False,
        system_fresh=True,
        calibration_fresh=True,
        profiles_fresh=True,
        readiness_fresh=True,
        hardware_age_sec=4.2,
        stale_after_sec=3.0,
    )
    assert payload['ready'] is False
    assert payload['blockingNode'] == 'runtime_supervisor:hardware'
    assert payload['terminalFaultReason'] == 'stale_hardware'
    assert payload['phaseHealth']['hardware']['ageSec'] == 4.2


def test_managed_lifecycle_payload_surfaces_non_active_nodes() -> None:
    failures = summarize_node_failures([('motion', ['node_a', 'node_b'])], {'node_a': 'active', 'node_b': 'inactive'})
    assert failures == [{'layer': 'motion', 'name': 'node_b', 'state': 'inactive'}]
    failed_phase, reason = first_failed_phase({'hardware': {'seen': True, 'fresh': True}, 'system': {'seen': False, 'fresh': False}})
    assert failed_phase == 'system'
    assert reason == 'missing_system'
