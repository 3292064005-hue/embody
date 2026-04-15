from arm_camera_driver import CameraDriverNode
from arm_perception import PerceptionNode


def test_perception_stream_updates_tracker_liveness_and_availability():
    camera = CameraDriverNode(source_type='mock', stale_after_sec=0.5, mock_profile='authoritative_demo')
    node = PerceptionNode(stale_after_sec=0.5, min_seen_count=2)
    first = node.process_summary(camera.capture_once(), now=1.0)
    assert first['perceptionAlive'] is True
    assert first['targetAvailable'] is False
    second = node.process_summary(camera.capture_once(), now=1.1)
    assert second['targetAvailable'] is True
    assert second['authoritativeVisualSource'] == 'synthetic_perception'
    assert node.health_snapshot(now=2.0, stale_after_sec=0.5)['perceptionAlive'] is False
