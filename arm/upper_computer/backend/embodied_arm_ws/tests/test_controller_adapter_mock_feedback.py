from arm_motion_executor.controller_adapter import ControllerAdapter


def test_controller_adapter_tracks_command_lifecycle():
    adapter = ControllerAdapter()
    result = adapter.send_command({'command_id': 'cmd-1', 'kind': 'EXEC_STAGE'})
    assert result.accepted is True
    assert result.state == 'dispatching'
    assert adapter.wait_feedback('cmd-1')['status'] == 'dispatching'
    assert adapter.cancel_command('cmd-1')['status'] == 'canceled'



def test_controller_adapter_accepts_runtime_feedback():
    adapter = ControllerAdapter()
    adapter.send_command({'command_id': 'cmd-2', 'kind': 'EXEC_STAGE'})
    updated = adapter.accept_feedback({'command_id': 'cmd-2', 'status': 'done', 'source': 'hardware', 'message': 'ok'})
    assert updated['status'] == 'done'
    assert updated['source'] == 'hardware'
    assert adapter.wait_feedback('cmd-2')['message'] == 'ok'
