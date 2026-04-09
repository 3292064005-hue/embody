from arm_camera_driver import CameraDriverNode, CaptureFrame


def test_camera_driver_topic_mode_updates_health_from_external_frames():
    node = CameraDriverNode(source_type='topic', stale_after_sec=0.5)
    payload = node.receive_frame(CaptureFrame(width=320, height=240, frame_id='camera', payload=[[1]]), now=1.0)
    assert payload['health']['cameraAlive'] is True
    assert node.health_snapshot(now=2.0)['cameraAlive'] is False
