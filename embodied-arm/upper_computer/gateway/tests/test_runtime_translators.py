from __future__ import annotations

from gateway.runtime_translators import (
    apply_diagnostics_payload,
    apply_readiness_payload,
    apply_targets_payload,
    apply_task_status_payload,
)
from gateway.state import GatewayState


class _Publisher:
    def __init__(self) -> None:
        self.calls: list[tuple] = []

    def publish_topics_threadsafe(self, *topics, extra_events=None) -> None:
        self.calls.append((topics, tuple(extra_events or ())))


def test_apply_diagnostics_payload_marks_state_authoritative_and_publishes() -> None:
    state = GatewayState()
    publisher = _Publisher()
    applied = apply_diagnostics_payload(state, publisher, {'ready': False, 'detail': 'warming_up', 'latencyMs': 'bad'})
    diagnostics = state.get_diagnostics()
    assert applied is True
    assert diagnostics['ready'] is False
    assert diagnostics['degraded'] is True
    assert diagnostics['latencyMs'] == 0.0
    assert publisher.calls[-1][0] == ('diagnostics',)


def test_apply_targets_payload_ignores_invalid_payloads_and_updates_targets() -> None:
    state = GatewayState()
    publisher = _Publisher()
    assert apply_targets_payload(state, publisher, {'targets': ['bad']}) is False
    applied = apply_targets_payload(state, publisher, {'targets': [{'id': 't1', 'pixelX': 'bad', 'worldY': '2.5', 'confidence': 'oops'}]})
    targets = state.get_targets()
    assert applied is True
    assert len(targets) == 1
    assert targets[0]['pixelX'] == 0.0
    assert targets[0]['worldY'] == 2.5
    assert targets[0]['confidence'] == 0.0
    assert publisher.calls[-1][0] == ('targets', 'readiness', 'diagnostics')


def test_apply_task_and_readiness_payloads_update_projection() -> None:
    state = GatewayState()
    publisher = _Publisher()
    assert apply_task_status_payload(state, publisher, {'taskId': 'task-1', 'stage': 'execute', 'progress': 'nan', 'retryCount': 'bad'}) is True
    task = state.get_current_task()
    assert task is not None
    assert task['taskId'] == 'task-1'
    assert task['percent'] == 0
    assert task['retryCount'] == 0
    assert apply_readiness_payload(state, publisher, {'allReady': True, 'modeReady': True, 'runtimeHealthy': True, 'checks': {}}) is True
    readiness = state.get_readiness()
    assert readiness['allReady'] is True
    assert publisher.calls[-1][0] == ('readiness', 'diagnostics')
