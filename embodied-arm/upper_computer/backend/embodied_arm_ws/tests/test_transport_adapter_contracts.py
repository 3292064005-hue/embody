from arm_motion_executor.transport_adapter import build_transport_adapter


def _ros2_submit(command: dict) -> tuple[bool, str]:
    _ros2_submit.calls.append(dict(command))
    return True, 'queued for ros2_control'


_ros2_submit.calls = []


def _publisher(payload: str) -> None:
    _publisher.calls.append(payload)


_publisher.calls = []


def test_ros2_control_live_requires_hardware_forwarding() -> None:
    adapter = build_transport_adapter(forward_hardware_commands=False, execution_mode='ros2_control_live', publish_json=_publisher, submit_ros2_control_command=_ros2_submit)
    result = adapter.dispatch({'command_id': 'cmd-1'})
    assert result.accepted is False
    assert result.transport_mode == 'rejected'
    assert 'requires forward_hardware_commands=true' in result.message


def test_ros2_control_live_rejects_incomplete_command_payload() -> None:
    _publisher.calls.clear()
    _ros2_submit.calls.clear()
    adapter = build_transport_adapter(forward_hardware_commands=True, execution_mode='ros2_control_live', publish_json=_publisher, submit_ros2_control_command=_ros2_submit)
    result = adapter.dispatch({'command_id': 'cmd-1', 'plan_id': '', 'task_id': 't', 'stage': 's', 'kind': 'HOME', 'timeout_sec': 1.0})
    assert result.accepted is False
    assert _publisher.calls == []
    assert 'missing required transport fields' in result.message


def test_forwarding_wraps_transport_contract_metadata() -> None:
    _publisher.calls.clear()
    adapter = build_transport_adapter(forward_hardware_commands=True, execution_mode='authoritative_simulation', publish_json=_publisher)
    result = adapter.dispatch({'command_id': 'cmd-2', 'plan_id': 'plan-1', 'task_id': 'task-1', 'stage': 'go_home', 'kind': 'HOME', 'timeout_sec': 1.0})
    assert result.accepted is True
    assert result.forwarded is True
    assert _publisher.calls
    assert 'authoritative_execution_v1' in _publisher.calls[0]


def test_ros2_control_live_submits_execution_target_sequentially() -> None:
    _publisher.calls.clear()
    _ros2_submit.calls.clear()
    adapter = build_transport_adapter(forward_hardware_commands=True, execution_mode='ros2_control_live', publish_json=_publisher, submit_ros2_control_command=_ros2_submit)
    result = adapter.dispatch({
        'command_id': 'cmd-3',
        'plan_id': 'plan-3',
        'task_id': 'task-3',
        'stage': 'approach',
        'kind': 'EXEC_STAGE',
        'timeout_sec': 2.0,
        'execution_target': {
            'joint_names': ['joint_1', 'joint_2'],
            'points': [
                {'positions': [0.1, 0.2], 'time_from_start_sec': 1.0},
            ],
        },
    })
    assert result.accepted is True
    assert result.forwarded is True
    assert result.transport_mode == 'ros2_control_trajectory'
    assert adapter.requires_sequential_dispatch() is True
    assert _publisher.calls == []
    assert _ros2_submit.calls and _ros2_submit.calls[0]['command_id'] == 'cmd-3'
