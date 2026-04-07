from arm_camera_driver import CameraDriverNode, CaptureFrame
from arm_perception import PerceptionNode


class StaticDetector:
    def __init__(self, output):
        self._output = output

    def detect(self, frame):
        return list(self._output)


def test_topic_ingress_frame_contract_reaches_authoritative_primary_target():
    camera = CameraDriverNode(source_type='topic', stale_after_sec=1.0)
    perception = PerceptionNode(stale_after_sec=1.0, min_seen_count=1)
    target = {
        'target_id': 't-red',
        'target_type': 'cube',
        'semantic_label': 'red',
        'x': 0.12,
        'y': 0.34,
        'confidence': 0.98,
    }
    perception.color = StaticDetector([target])
    perception.qrcode = StaticDetector([])
    perception.contour = StaticDetector([])

    frame_summary = camera.receive_frame(
        CaptureFrame(width=320, height=240, frame_id='camera_optical_frame', payload=[[1, 2], [3, 4]]),
        now=1.0,
    )
    result = perception.process_summary(frame_summary, now=1.1)

    assert frame_summary['health']['cameraAlive'] is True
    assert result['perceptionAlive'] is True
    assert result['targetAvailable'] is True
    assert result['primaryTarget'] is not None
    assert result['primaryTarget']['target_id'] == 't-red'
    assert result['primaryTarget']['semantic_label'] == 'red'
