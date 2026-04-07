from __future__ import annotations

import importlib
from types import SimpleNamespace

import pytest

from gateway.models import build_command_summary, build_readiness_layers, default_readiness, map_hardware_state_message


def test_default_readiness_exposes_layered_fields():
    payload = default_readiness()
    assert payload['runtimeHealthy'] is False
    assert payload['modeReady'] is False
    assert payload['allReady'] is False
    assert 'commandSummary' in payload
    assert payload['commandSummary']['blockedCount'] == len(payload['commandPolicies'])


def test_build_readiness_layers_distinguishes_runtime_and_mode():
    checks = {
        'ros2': {'ok': True},
        'task_orchestrator': {'ok': True},
        'motion_planner': {'ok': True},
        'motion_executor': {'ok': True},
        'hardware_bridge': {'ok': True},
        'calibration': {'ok': True},
        'profiles': {'ok': True},
        'camera_alive': {'ok': False},
        'perception_alive': {'ok': False},
        'target_available': {'ok': False},
    }
    runtime_healthy, mode_ready = build_readiness_layers('task', checks)
    assert runtime_healthy is True
    assert mode_ready is False


def test_map_hardware_state_message_preserves_authority_and_simulation_flags():
    msg = SimpleNamespace(
        joint_positions=[0.0] * 5,
        gripper_open=True,
        homed=True,
        limit_triggered=[False] * 5,
        pose_name='home',
        busy=False,
        error_code='',
        stm32_online=True,
        esp32_online=False,
        raw_status='{"transportMode":"simulated","hardwareAuthoritative":false,"hardwareControllable":false,"simulatedTransport":true,"simulatedFallback":true}',
        hardware_ready=False,
    )
    payload = map_hardware_state_message(msg)
    assert payload['sourceStm32Online'] is True
    assert payload['sourceStm32Authoritative'] is False
    assert payload['sourceStm32TransportMode'] == 'simulated'
    assert payload['sourceStm32Controllable'] is False
    assert payload['sourceStm32Simulated'] is True
    assert payload['sourceStm32SimulatedFallback'] is True


def test_build_command_summary_counts_allowed_and_blocked():
    summary = build_command_summary({
        'startTask': {'allowed': True},
        'jog': {'allowed': False},
        'home': {'allowed': True},
    })
    assert summary == {
        'allowed': ['startTask', 'home'],
        'blocked': ['jog'],
        'readyCount': 2,
        'blockedCount': 1,
    }


def test_server_rejects_wildcard_origin_when_credentials_enabled(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv('EMBODIED_ARM_CORS_ALLOW_ORIGINS', '*')
    monkeypatch.setenv('EMBODIED_ARM_CORS_ALLOW_CREDENTIALS', 'true')
    with pytest.raises(RuntimeError, match='credentialed CORS'):
        import gateway.server as server
        importlib.reload(server)


def test_map_hardware_state_message_prefers_hardware_presence_from_raw_status():
    msg = SimpleNamespace(
        joint_position=[0.0] * 5,
        home_ok=True,
        motion_busy=False,
        hardware_fault_code=0,
        stm32_online=False,
        esp32_online=False,
        raw_status='{"hardwarePresent": true, "hardwareAuthoritative": false, "hardwareControllable": false, "transportMode": "real"}',
        limit_triggered=False,
    )
    payload = map_hardware_state_message(msg)
    assert payload['sourceStm32Online'] is True
    assert payload['sourceStm32Authoritative'] is False
    assert payload['sourceStm32Controllable'] is False
    assert payload['sourceStm32TransportMode'] == 'real'
