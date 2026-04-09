from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / 'src'
ARM_MSGS = ROOT / 'arm_msgs'
ARM_INTERFACES = ROOT / 'arm_interfaces'


def test_arm_interfaces_mirrors_arm_msgs_layout():
    for sub in ('msg', 'srv', 'action'):
        left = sorted(p.name for p in (ARM_MSGS / sub).glob('*'))
        right = sorted(p.name for p in (ARM_INTERFACES / sub).glob('*'))
        assert left == right, f'{sub} interface mirror mismatch'
