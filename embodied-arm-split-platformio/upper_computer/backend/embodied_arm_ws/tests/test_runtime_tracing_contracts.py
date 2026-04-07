from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / 'src'


def test_task_orchestrator_rebuild_path_reuses_runtime_hook_builder() -> None:
    text = (ROOT / 'arm_task_orchestrator' / 'arm_task_orchestrator' / 'task_orchestrator_node.py').read_text(encoding='utf-8')
    assert 'def _build_runtime_hooks(self):' in text
    assert 'self._runtime_hooks = self._build_runtime_hooks()' in text
    assert 'self._runtime_coordinator = RuntimeCoordinator(' in text


def test_split_stack_runtime_contracts_propagate_correlation_and_task_run_ids() -> None:
    planner_text = (ROOT / 'arm_motion_planner' / 'arm_motion_planner' / 'motion_planner_node.py').read_text(encoding='utf-8')
    executor_text = (ROOT / 'arm_motion_executor' / 'arm_motion_executor' / 'motion_executor_node.py').read_text(encoding='utf-8')
    runtime_text = (ROOT / 'arm_task_orchestrator' / 'arm_task_orchestrator' / 'runtime.py').read_text(encoding='utf-8')
    assert "payload.get('correlationId'" in planner_text
    assert "payload.get('taskRunId'" in planner_text
    assert "payload.get('correlationId'" in executor_text
    assert "payload.get('taskRunId'" in executor_text
    assert "correlation_id=getattr(self._state.current, 'correlation_id', '')" in runtime_text
    assert "task_run_id=getattr(self._state.current, 'task_run_id', '')" in runtime_text
