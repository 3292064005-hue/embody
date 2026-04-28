from arm_camera_driver import FramePublisher, CaptureFrame


def test_frame_publisher_includes_timestamp_and_source_metadata():
    summary = FramePublisher().to_summary(CaptureFrame(width=10, height=20, frame_id='frame', payload=[]), timestamp_sec=123.4, source_metadata={'sourceType': 'mock'})
    assert summary['timestampSec'] == 123.4
    assert summary['sourceMetadata']['sourceType'] == 'mock'
