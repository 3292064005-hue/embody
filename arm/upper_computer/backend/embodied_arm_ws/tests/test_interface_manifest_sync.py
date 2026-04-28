from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / 'src' / 'arm_msgs'


def test_cmakelists_registers_all_declared_interfaces():
    cmake = (ROOT / 'CMakeLists.txt').read_text(encoding='utf-8')
    for rel in sorted((ROOT / 'msg').glob('*.msg')):
        assert rel.name in cmake, f'message {rel.name} missing from CMakeLists.txt'
    for rel in sorted((ROOT / 'srv').glob('*.srv')):
        assert rel.name in cmake, f'service {rel.name} missing from CMakeLists.txt'
    for rel in sorted((ROOT / 'action').glob('*.action')):
        assert rel.name in cmake, f'action {rel.name} missing from CMakeLists.txt'
