from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / 'src'
LEGACY_MAINS = {
    'arm_task_manager': ROOT / 'arm_task_manager' / 'arm_task_manager' / 'task_manager_node.py',
    'arm_motion_bridge': ROOT / 'arm_motion_bridge' / 'arm_motion_bridge' / 'motion_bridge_node.py',
    'arm_lifecycle_manager': ROOT / 'arm_lifecycle_manager' / 'arm_lifecycle_manager' / 'lifecycle_manager_node.py',
}


def test_legacy_nodes_emit_deprecation_warning_in_main():
    for name, path in LEGACY_MAINS.items():
        text = path.read_text(encoding='utf-8')
        assert 'warnings.warn(' in text, f'{name} should explicitly warn about deprecation'
