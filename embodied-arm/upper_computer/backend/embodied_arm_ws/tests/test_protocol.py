from arm_backend_common.enums import HardwareCommand
from arm_backend_common.protocol import Frame, build_frame, crc16, decode_payload, decode_hex_frame, encode_payload



def test_frame_roundtrip() -> None:
    frame = build_frame(HardwareCommand.HOME, 7, {'kind': 'HOME', 'task_id': 'abc'})
    decoded = Frame.decode(frame.encode())
    assert decoded.command == int(HardwareCommand.HOME)
    assert decoded.sequence == 7
    assert decode_payload(decoded.payload)['task_id'] == 'abc'



def test_crc_mismatch_is_rejected() -> None:
    frame = build_frame(HardwareCommand.QUERY_STATE, 3, {'kind': 'QUERY_STATE'})
    raw = bytearray(frame.encode())
    raw[-3] ^= 0x01
    try:
        Frame.decode(bytes(raw))
    except ValueError as exc:
        assert 'CRC mismatch' in str(exc)
    else:  # pragma: no cover - defensive failure path
        raise AssertionError('CRC mismatch should be rejected')



def test_invalid_frame_boundary_is_rejected() -> None:
    frame = build_frame(HardwareCommand.RESET_FAULT, 2, {'kind': 'RESET_FAULT'}).encode()
    try:
        Frame.decode(frame[1:])
    except ValueError as exc:
        assert 'boundary' in str(exc)
    else:  # pragma: no cover
        raise AssertionError('invalid frame boundary should be rejected')



def test_payload_roundtrip_supports_servo_and_query_state_contracts() -> None:
    servo_payload = {'kind': 'SERVO_CARTESIAN', 'axis': 'x', 'delta': 0.02, 'task_id': 'manual'}
    query_payload = {'kind': 'QUERY_STATE', 'task_id': 'system'}
    servo = encode_payload(servo_payload)
    query = encode_payload(query_payload)
    assert decode_payload(servo) == servo_payload
    assert decode_payload(query) == query_payload



def test_decode_hex_frame_roundtrip() -> None:
    frame = build_frame(HardwareCommand.ACK, 11, {'kind': 'ACK', 'status': 'accepted'})
    decoded = decode_hex_frame(frame.encode().hex())
    assert decoded.command == int(HardwareCommand.ACK)
    assert crc16(frame.encode()[2:-4]) > 0
