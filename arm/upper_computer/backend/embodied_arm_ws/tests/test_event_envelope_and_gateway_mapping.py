from arm_backend_common.event_envelope import decode_event_message, encode_event_message
from gateway.models import map_log_event_message


class _TaskEvent:
    level = 'ERROR'
    source = 'task_orchestrator'
    event_type = 'FAULT'
    task_id = 'task-1'
    code = 42
    message = encode_event_message(
        'planner rejected target',
        request_id='req-1',
        correlation_id='corr-1',
        stage='plan',
        error_code='planning_rejected',
        operator_actionable=True,
        payload={'reason': 'collision'},
    )


def test_event_envelope_roundtrip():
    raw = encode_event_message('hello', request_id='req-1', stage='plan', payload={'x': 1})
    payload = decode_event_message(raw)
    assert payload is not None
    assert payload['message'] == 'hello'
    assert payload['requestId'] == 'req-1'
    assert payload['stage'] == 'plan'
    assert payload['payload']['x'] == 1


def test_gateway_mapping_extracts_structured_event_envelope():
    mapped = map_log_event_message(_TaskEvent())
    assert mapped['message'] == 'planner rejected target'
    assert mapped['requestId'] == 'req-1'
    assert mapped['correlationId'] == 'corr-1'
    assert mapped['stage'] == 'plan'
    assert mapped['errorCode'] == 'planning_rejected'
    assert mapped['operatorActionable'] is True
    assert mapped['payload']['reason'] == 'collision'
    assert mapped['payload']['code'] == 42
