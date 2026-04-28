from arm_perception import TargetTracker
from arm_backend_common.data_models import TargetSnapshot


def test_target_tracker_exposes_runtime_health_and_best_target():
    tracker = TargetTracker(stale_after_sec=1.0, min_seen_count=2)
    first = TargetSnapshot(target_id='t1', target_type='cube', semantic_label='red', table_x=0.1, table_y=0.1, confidence=0.9)
    tracker.ingest_batch([first], now=1.0)
    assert tracker.health_snapshot(now=1.0)['targetAvailable'] is False
    second = TargetSnapshot(target_id='t1', target_type='cube', semantic_label='red', table_x=0.1, table_y=0.1, confidence=0.95)
    tracker.ingest_batch([second], now=1.1)
    assert tracker.best_target('red', now=1.1).target_id == 't1'
    tracker.prune(now=2.5)
    assert tracker.health_snapshot(now=2.5)['trackedTargetCount'] == 0
