from pathlib import Path


def test_real_and_hybrid_launch_use_supported_camera_source_values():
    launch_factory = Path(__file__).resolve().parents[1] / 'src' / 'arm_bringup' / 'arm_bringup' / 'launch_factory.py'
    text = launch_factory.read_text()
    assert "camera_source='camera'" not in text
    assert text.count("camera_source='topic'") >= 2
