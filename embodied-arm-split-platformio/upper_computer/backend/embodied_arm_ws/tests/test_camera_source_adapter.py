from arm_camera_driver import MockCameraSource, TopicCameraSource, CaptureFrame


def test_camera_source_adapters_provide_frames():
    frame = MockCameraSource().read_frame()
    assert frame.width == 640
    source = TopicCameraSource()
    source.update(CaptureFrame(width=320, height=240, frame_id='camera', payload=[[1]]), received_monotonic=1.0)
    assert source.read_frame().width == 320
