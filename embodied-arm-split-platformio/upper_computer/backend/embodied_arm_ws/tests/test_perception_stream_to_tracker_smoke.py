from arm_perception import PerceptionNode


class StaticDetector:
    def __init__(self, output):
        self._output = output

    def detect(self, frame):
        return list(self._output)


def test_perception_stream_updates_tracker_liveness_and_availability():
    node = PerceptionNode(stale_after_sec=0.5, min_seen_count=2)
    node.color = StaticDetector([{'target_id': 't1', 'target_type': 'cube', 'semantic_label': 'red', 'x': 0.1, 'y': 0.2, 'confidence': 0.9}])
    node.qrcode = StaticDetector([])
    node.contour = StaticDetector([])
    first = node.receive_frame([[0]], now=1.0)
    assert first['perceptionAlive'] is True
    assert first['targetAvailable'] is False
    second = node.receive_frame([[0]], now=1.1)
    assert second['targetAvailable'] is True
    assert node.health_snapshot(now=2.0, stale_after_sec=0.5)['perceptionAlive'] is False
