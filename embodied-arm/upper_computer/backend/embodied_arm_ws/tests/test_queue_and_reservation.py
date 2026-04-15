from types import SimpleNamespace

from arm_backend_common.data_models import TargetSnapshot, TaskContext, TaskProfile, TaskRequest
from arm_perception import VisionTargetTracker
from arm_task_orchestrator.task_plugins import ContinuousPlugin
from arm_task_orchestrator.task_queue import TaskQueue


def test_task_queue_fifo():
    queue = TaskQueue(capacity=2)
    assert queue.push(TaskRequest(task_id='a', task_type='PICK_AND_PLACE'))
    assert queue.push(TaskRequest(task_id='b', task_type='PICK_AND_PLACE'))
    assert not queue.push(TaskRequest(task_id='c', task_type='PICK_AND_PLACE'))
    assert queue.pop().task_id == 'a'
    assert queue.pop().task_id == 'b'
    assert queue.pop() is None


def test_continuous_plugin_skips_completed_targets():
    tracker = VisionTargetTracker(stale_after_sec=1.0, min_seen_count=1)
    first = TargetSnapshot(target_id='t1', target_type='cube', semantic_label='red', confidence=0.9)
    second = TargetSnapshot(target_id='t2', target_type='cube', semantic_label='blue', confidence=0.8)
    tracker.upsert(first, now=1.0)
    tracker.upsert(second, now=1.0)

    current = TaskContext(task_id='clear-1', task_type='CLEAR_TABLE')
    current.completed_target_ids.add(first.key())
    state = SimpleNamespace(current=current, task_profile=TaskProfile(clear_table_max_items=4))
    engine = SimpleNamespace(state=state, tracker=tracker)

    selected = ContinuousPlugin().select_target(engine)
    assert selected is not None
    assert selected.target_id == 't2'
