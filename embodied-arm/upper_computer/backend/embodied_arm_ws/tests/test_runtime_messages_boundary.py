from __future__ import annotations

from types import SimpleNamespace

import arm_common.runtime_messages as runtime_messages


class _FakeTaskStatus:
    def __init__(self) -> None:
        self.task_id = ''
        self.task_type = ''
        self.stage = ''
        self.target_id = ''
        self.place_profile = ''
        self.retry_count = 0
        self.max_retry = 0
        self.active = False
        self.cancel_requested = False
        self.message = ''
        self.progress = 0.0


class _FakeTargetInfo:
    def __init__(self) -> None:
        self.target_id = ''
        self.target_type = ''
        self.semantic_label = ''
        self.image_u = 0.0
        self.image_v = 0.0
        self.table_x = 0.0
        self.table_y = 0.0
        self.yaw = 0.0
        self.confidence = 0.0
        self.is_valid = False


class _FakeTargetArray:
    def __init__(self) -> None:
        self.targets = []
        self.header = SimpleNamespace(stamp=None)



class _FakeBringupStatus:
    def __init__(self) -> None:
        self.ready = False
        self.managed_lifecycle = False
        self.autostart_complete = False
        self.all_active = False
        self.current_layer = ''
        self.blocking_node = ''
        self.terminal_fault_reason = ''
        self.raw_json = ''


def test_build_task_status_message_coerces_invalid_numbers(monkeypatch):
    monkeypatch.setattr(runtime_messages, 'TaskStatusMsg', _FakeTaskStatus)
    msg = runtime_messages.build_task_status_message({
        'taskId': 'task-1',
        'retryCount': 'bad',
        'maxRetry': '-3',
        'active': 'true',
        'cancelRequested': 'false',
        'progress': 'nan',
    })
    assert msg.retry_count == 0
    assert msg.max_retry == 0
    assert msg.active is True
    assert msg.cancel_requested is False
    assert msg.progress == 0.0


def test_build_target_array_message_skips_invalid_entries_and_coerces_values(monkeypatch):
    monkeypatch.setattr(runtime_messages, 'TargetArray', _FakeTargetArray)
    monkeypatch.setattr(runtime_messages, 'TargetInfo', _FakeTargetInfo)
    msg = runtime_messages.build_target_array_message({
        'targets': [
            {'id': 'target-1', 'pixelX': 'bad', 'worldY': '2.0', 'confidence': 'oops', 'graspable': 'false'},
            'not-a-dict',
        ]
    })
    assert len(msg.targets) == 1
    target = msg.targets[0]
    assert target.target_id == 'target-1'
    assert target.image_u == 0.0
    assert target.table_y == 2.0
    assert target.confidence == 0.0
    assert target.is_valid is False


def test_build_and_parse_bringup_status_message_roundtrip(monkeypatch):
    monkeypatch.setattr(runtime_messages, 'BringupStatus', _FakeBringupStatus)
    msg = runtime_messages.build_bringup_status_message({
        'ready': 'true',
        'managedLifecycle': True,
        'autostartComplete': 'false',
        'allActive': 'true',
        'currentLayer': 'motion',
        'blockingNode': 'motion_executor_node',
        'terminalFaultReason': 'activate failed',
        'cleanupFailures': {'motion_executor_node': 'destroy failed'},
    })
    parsed = runtime_messages.parse_bringup_status_message(msg)
    assert msg.ready is True
    assert msg.autostart_complete is False
    assert parsed['managedLifecycle'] is True
    assert parsed['blockingNode'] == 'motion_executor_node'
    assert parsed['cleanupFailures']['motion_executor_node'] == 'destroy failed'
