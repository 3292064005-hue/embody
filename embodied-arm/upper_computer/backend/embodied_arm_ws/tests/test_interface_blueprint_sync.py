from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / 'src' / 'arm_interfaces'


def test_cmakelists_registers_blueprint_interfaces():
    text = (ROOT / 'CMakeLists.txt').read_text(encoding='utf-8')
    for rel in [
        'msg/Target.msg', 'msg/TargetArray.msg', 'msg/EventLog.msg', 'msg/GraspCandidate.msg',
        'srv/Stop.srv', 'srv/CaptureCalibrationFrame.srv',
        'action/Homing.action', 'action/Recover.action',
    ]:
        assert rel in text
