import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / 'src' / 'arm_task_orchestrator' / 'arm_task_orchestrator'


def test_task_status_topic_is_published_and_stop_alias_exists():
    text = (ROOT / 'task_orchestrator_node.py').read_text(encoding='utf-8')
    assert '/arm/task/status' in text
    assert "'/arm/stop'" in text or '"/arm/stop"' in text
    assert '/arm/internal/stop_cmd' in text
