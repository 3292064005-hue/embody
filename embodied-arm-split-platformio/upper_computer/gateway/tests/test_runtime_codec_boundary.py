from __future__ import annotations

from types import SimpleNamespace

from gateway.runtime_codec import (
    decode_diagnostics_summary_message,
    decode_target_array_message,
    decode_task_status_message,
)


def test_decode_task_status_message_coerces_malformed_numeric_fields():
    payload = decode_task_status_message(
        SimpleNamespace(
            task_id='task-1',
            task_type='pick_place',
            stage='execute',
            target_id='target-1',
            place_profile='bin_red',
            retry_count='bad',
            max_retry='-3',
            active='true',
            cancel_requested='false',
            message='running',
            progress='nan',
        )
    )
    assert payload['retryCount'] == 0
    assert payload['maxRetry'] == 0
    assert payload['active'] is True
    assert payload['cancelRequested'] is False
    assert payload['progress'] == 0.0


def test_decode_target_array_message_coerces_malformed_coordinates():
    item = SimpleNamespace(
        target_id='t1',
        semantic_label='red',
        target_type='cube',
        image_u='bad',
        image_v=None,
        table_x='nan',
        table_y='2.5',
        yaw='bad-angle',
        confidence='oops',
        is_valid='true',
    )
    payload = decode_target_array_message(SimpleNamespace(targets=[item]))
    assert payload['targetCount'] == 1
    target = payload['targets'][0]
    assert target['pixelX'] == 0.0
    assert target['pixelY'] == 0.0
    assert target['worldX'] == 0.0
    assert target['worldY'] == 2.5
    assert target['angle'] == 0.0
    assert target['confidence'] == 0.0
    assert target['graspable'] is True


def test_decode_diagnostics_summary_message_marks_not_ready_as_degraded():
    payload = decode_diagnostics_summary_message(
        SimpleNamespace(ready=False, detail='warming_up', latency_ms='bad', task_success_rate='95.5')
    )
    assert payload['ready'] is False
    assert payload['degraded'] is True
    assert payload['detail'] == 'warming_up'
    assert payload['latencyMs'] == 0.0
    assert payload['taskSuccessRate'] == 95.5
