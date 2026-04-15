from gateway.state import GatewayState


def test_attach_request_context_keeps_distinct_episode_id() -> None:
    state = GatewayState()
    request_id, correlation_id, task_run_id = state.attach_request_context('task-1', 'req-1', episode_id='episode-1')
    assert request_id == 'req-1'
    assert correlation_id
    assert task_run_id
    payload = state.request_context_payload('task-1')
    assert payload is not None
    assert payload['taskRunId'] == task_run_id
    assert payload['episodeId'] == 'episode-1'


def test_start_task_projects_episode_id_separately_from_task_run_id() -> None:
    state = GatewayState()
    current = state.start_task('task-ep', 'pick_place', request_id='req-ep', task_run_id='taskrun-ep', episode_id='episode-ep')
    assert current['taskRunId'] == 'taskrun-ep'
    assert current['episodeId'] == 'episode-ep'
