import time

from arm_camera_driver import CameraDriverNode, CameraHealthMonitor
from arm_perception import PerceptionNode


def test_camera_health_snapshot_reports_alive_after_frame():
    monitor = CameraHealthMonitor()
    now = time.monotonic()
    monitor.frame_received(now)
    snapshot = monitor.snapshot(now + 0.1, stale_after_sec=1.0)
    assert snapshot['cameraAlive'] is True
    assert snapshot['lastFrameAgeSec'] is not None


def test_camera_driver_capture_once_includes_health_summary():
    node = CameraDriverNode()
    payload = node.capture_once()
    assert 'health' in payload
    assert 'cameraAlive' in payload['health']


def test_perception_node_health_snapshot_separates_liveness_and_target_availability():
    node = PerceptionNode()
    node.process([[0]])
    snapshot = node.health_snapshot()
    assert 'perceptionAlive' in snapshot
    assert 'targetAvailable' in snapshot



def test_camera_driver_capture_once_marks_reconnect_on_source_failure(monkeypatch):
    node = CameraDriverNode(source_type='topic')
    try:
        node.capture_once()
    except RuntimeError:
        pass
    snapshot = node.health_snapshot()
    assert snapshot['cameraAlive'] is False
    assert snapshot['deviceOpen'] is False
    assert snapshot['reconnectCount'] >= 1
    assert snapshot['droppedFrameCount'] >= 1
