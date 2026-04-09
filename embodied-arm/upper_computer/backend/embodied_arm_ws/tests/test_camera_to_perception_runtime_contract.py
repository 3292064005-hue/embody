from arm_camera_driver import CameraDriverNode
from arm_perception import PerceptionNode


def test_authoritative_mock_runtime_produces_primary_target():
    camera = CameraDriverNode(source_type='mock', stale_after_sec=1.0, mock_profile='authoritative_demo')
    perception = PerceptionNode(stale_after_sec=1.0, min_seen_count=1)
    frame_summary = camera.capture_once()
    result = perception.process_summary(frame_summary, now=1.1)

    assert frame_summary['health']['cameraAlive'] is True
    assert frame_summary['metadata']['mockProfile'] == 'authoritative_demo'
    assert result['perceptionAlive'] is True
    assert result['targetAvailable'] is True
    assert result['primaryTarget'] is not None
    assert result['primaryTarget']['semantic_label'] == 'green'
