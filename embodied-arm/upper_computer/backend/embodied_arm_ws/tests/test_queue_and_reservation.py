from arm_backend_common.data_models import TargetSnapshot, TaskRequest
from arm_task_manager.mission_queue import MissionQueue
from arm_task_manager.target_reservation import TargetReservationManager


def test_mission_queue_fifo():
    queue = MissionQueue(max_size=2)
    assert queue.push(TaskRequest(task_id='a', task_type='PICK'))
    assert queue.push(TaskRequest(task_id='b', task_type='PICK'))
    assert not queue.push(TaskRequest(task_id='c', task_type='PICK'))
    assert queue.pop().task_id == 'a'
    assert queue.pop().task_id == 'b'
    assert queue.pop() is None


def test_target_reservation_exclusive():
    manager = TargetReservationManager(reserve_timeout_sec=1.0)
    target = TargetSnapshot(target_id='t1', target_type='block', semantic_label='red')
    assert manager.reserve('task_a', target, now=1.0)
    assert not manager.reserve('task_b', target, now=1.1)
    manager.release('task_a', target)
    assert manager.reserve('task_b', target, now=1.2)
