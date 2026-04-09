from __future__ import annotations

import time
from pathlib import Path

import yaml

import gateway.runtime_config as runtime_config
from gateway.runtime_config import clear_runtime_config_caches
from gateway.state import GatewayState


def test_gateway_readiness_projects_manual_limits_and_runtime_config_version(tmp_path: Path, monkeypatch) -> None:
    safety_path = tmp_path / 'safety_limits.yaml'
    safety_path.write_text(
        yaml.safe_dump({'manual_command_limits': {'max_servo_cartesian_delta': 0.1, 'max_jog_joint_step_deg': 10.0}}, sort_keys=False),
        encoding='utf-8',
    )
    monkeypatch.setattr(runtime_config, 'SAFETY_LIMITS_PATH', safety_path)
    clear_runtime_config_caches()

    state = GatewayState()
    first = state.get_readiness()
    assert first['manualCommandLimits'] == {
        'maxServoCartesianDeltaMeters': 0.1,
        'maxJogJointStepDeg': 10.0,
    }
    first_version = first['runtimeConfigVersion']

    time.sleep(0.01)
    safety_path.write_text(
        yaml.safe_dump({'manual_command_limits': {'max_servo_cartesian_delta': 0.02, 'max_jog_joint_step_deg': 3.0}}, sort_keys=False),
        encoding='utf-8',
    )

    second = state.get_readiness()
    assert second['manualCommandLimits'] == {
        'maxServoCartesianDeltaMeters': 0.02,
        'maxJogJointStepDeg': 3.0,
    }
    assert second['runtimeConfigVersion'] != first_version
