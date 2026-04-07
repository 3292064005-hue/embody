from gateway.state import GatewayState


def test_start_task_persists_request_correlation_and_task_run_context() -> None:
    state = GatewayState()
    current = state.start_task(
        'task-123',
        'pick_place',
        'red',
        request_id='req-123',
        correlation_id='corr-123',
        task_run_id='taskrun-123',
    )
    assert current['requestId'] == 'req-123'
    assert current['correlationId'] == 'corr-123'
    assert current['taskRunId'] == 'taskrun-123'
    assert state.request_context('task-123') == ('req-123', 'corr-123', 'taskrun-123')


def test_log_updates_keep_attached_request_context_payload() -> None:
    state = GatewayState()
    state.start_task(
        'task-ctx',
        'pick_place',
        request_id='req-ctx',
        correlation_id='corr-ctx',
        task_run_id='taskrun-ctx',
    )
    task, changed = state.update_task_from_log({
        'taskId': 'task-ctx',
        'event': 'TASK_ENQUEUED',
        'message': 'queued',
        'requestId': 'req-ctx',
        'correlationId': 'corr-ctx',
        'taskRunId': 'taskrun-ctx',
    })
    assert changed is True
    assert task is not None
    assert task['requestId'] == 'req-ctx'
    assert task['correlationId'] == 'corr-ctx'
    assert task['taskRunId'] == 'taskrun-ctx'
