from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CPP = ROOT / 'src' / 'arm_hardware_interface' / 'src' / 'embodied_arm_system.cpp'
DISPATCHER = ROOT / 'src' / 'arm_hardware_bridge' / 'arm_hardware_bridge' / 'hardware_command_dispatcher_node.py'


def test_hardware_interface_external_feedback_fails_closed_on_authority_and_staleness_bits() -> None:
    text = CPP.read_text(encoding='utf-8')
    assert 'hardwareAuthoritative' in text
    assert 'hardwareControllable' in text
    assert 'state_stale' in text
    assert '!hardware_authoritative_' in text
    assert '!hardware_controllable_' in text
    assert '|| state_stale_' in text


def test_dispatcher_explicitly_supports_set_joints_joint_stream_commands() -> None:
    text = DISPATCHER.read_text(encoding='utf-8')
    assert "'SET_JOINTS': HardwareCommand.SET_JOINTS" in text
    assert 'JOINT_STREAM_PRODUCERS' in text
    assert '_validate_command_origin' in text
