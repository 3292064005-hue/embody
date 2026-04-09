from arm_esp32_gateway import BoardHealthParser, VoiceEventClient
from arm_perception.synthetic_targets import extract_synthetic_targets


def test_board_health_parser_treats_error_status_as_offline_without_explicit_online():
    payload = BoardHealthParser().parse({'status': 'error', 'heartbeatCounter': 'bad', 'wifiRssi': 'nope'})
    assert payload['online'] is False
    assert payload['heartbeatCounter'] == 0
    assert payload['wifiRssi'] == -127


def test_voice_event_client_skips_empty_payloads_and_bad_timestamps():
    events = VoiceEventClient().parse_events([{'phrase': '', 'command': '', 'stampMs': 'bad'}, {'phrase': ' start ', 'stampMs': 'bad'}])
    assert len(events) == 1
    assert events[0]['phrase'] == 'start'
    assert events[0]['stampMs'] == 0


def test_extract_synthetic_targets_filters_invalid_ids_and_bad_numbers():
    frame = {'payload': {'targets': [
        {'id': '', 'x': '1.0'},
        {'id': 'ok-1', 'x': 'bad', 'y': '2.5', 'detectors': ['color']},
    ]}}
    targets = extract_synthetic_targets(frame, detector_name='color')
    assert len(targets) == 1
    assert targets[0]['target_id'] == 'ok-1'
    assert targets[0]['x'] == 0.0
    assert targets[0]['y'] == 2.5
