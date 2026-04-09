from __future__ import annotations

from gateway.ros_bridge import _safe_bool, _safe_float
from gateway.state import GatewayState


def test_gateway_state_preserves_authoritative_diagnostics_payload():
    state = GatewayState()
    state.set_diagnostics({
        'ready': False,
        'degraded': True,
        'detail': 'warming_up',
        'latencyMs': _safe_float('bad', 0.0),
        'taskSuccessRate': _safe_float('96.5', 0.0),
    }, authoritative=True)
    diagnostics = state.get_diagnostics()
    assert diagnostics['ready'] is False
    assert diagnostics['degraded'] is True
    assert diagnostics['detail'] == 'warming_up'
    assert diagnostics['latencyMs'] == 0.0
    assert diagnostics['taskSuccessRate'] == 96.5


def test_ros_bridge_safe_helpers_fail_closed_for_malformed_values():
    assert _safe_float('bad', 1.0) == 1.0
    assert _safe_float('nan', 2.0) == 2.0
    assert _safe_bool('false', True) is False
    assert _safe_bool('true', False) is True
