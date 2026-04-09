from __future__ import annotations

from types import SimpleNamespace

from gateway.models import map_hardware_state_message, map_system_state_message


def test_map_hardware_state_message_distinguishes_board_online_and_frame_ingress() -> None:
    msg = SimpleNamespace(
        joint_positions=[0.0] * 6,
        gripper_open=True,
        homed=True,
        limit_triggered=[False] * 6,
        pose_name='home',
        busy=False,
        error_code='',
        stm32_online=True,
        esp32_online=True,
        raw_status='{"esp32_link":{"online":true,"stream_semantic":"reserved","stream_reserved":true,"frame_ingress_live":false},"perception_alive":false}',
        hardware_ready=True,
    )
    payload = map_hardware_state_message(msg)
    assert payload['sourceEsp32Online'] is True
    assert payload['sourceEsp32StreamSemantic'] == 'reserved'
    assert payload['sourceEsp32StreamReserved'] is True
    assert payload['sourceCameraFrameIngressLive'] is False
    assert payload['sourcePerceptionLive'] is False



def test_map_system_state_message_does_not_promote_esp32_presence_to_camera_connected() -> None:
    system = map_system_state_message(
        {'mode': 'idle'},
        {
            'sourceStm32Online': True,
            'sourceEsp32Online': True,
            'sourceCameraFrameIngressLive': False,
        },
        {},
    )
    assert system['esp32Connected'] is True
    assert system['cameraConnected'] is False
