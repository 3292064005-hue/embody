from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / 'src' / 'arm_task_orchestrator' / 'arm_task_orchestrator'


def test_task_orchestrator_node_does_not_import_deprecated_task_manager_modules():
    text = (ROOT / 'task_orchestrator_node.py').read_text(encoding='utf-8')
    assert 'arm_task_manager.state_machine' not in text
    assert 'arm_task_manager.verification' not in text
