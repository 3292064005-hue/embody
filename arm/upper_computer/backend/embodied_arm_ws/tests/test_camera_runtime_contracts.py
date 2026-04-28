from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / 'src'
CAMERA_RUNTIME = ROOT / 'arm_camera_driver' / 'arm_camera_driver' / 'camera_runtime_node.py'
TOPIC_NAMES = ROOT / 'arm_common' / 'arm_common' / 'topic_names.py'


def test_camera_runtime_keeps_standard_and_compat_ingress_contracts() -> None:
    runtime_text = CAMERA_RUNTIME.read_text(encoding='utf-8')
    topics_text = TOPIC_NAMES.read_text(encoding='utf-8')
    assert "CAMERA_IMAGE_RAW = '/arm/camera/image_raw'" in topics_text
    assert "CAMERA_IMAGE_COMPAT = '/arm/camera/image_raw_compat'" in topics_text
    assert 'create_managed_publisher(Image, TopicNames.CAMERA_IMAGE_RAW, 10)' in runtime_text
    assert "create_subscription(String, str(self.get_parameter('legacy_topic_name').value), self._on_external_frame, 20)" in runtime_text
    assert "create_subscription(Image, str(self.get_parameter('topic_name').value), self._on_external_image, 20)" in runtime_text


def test_camera_runtime_compat_loopback_republish_is_fail_closed_by_default() -> None:
    runtime_text = CAMERA_RUNTIME.read_text(encoding='utf-8')
    assert "self.declare_parameter('republish_compat_frames_as_standard_image', False)" in runtime_text
    assert "self._publish_frame_summary(summary, publish_standard_image=self._should_publish_standard_image(source='compat'))" in runtime_text
