from __future__ import annotations

from pathlib import Path

import pytest

from arm_task_orchestrator.stack_factory import build_task_behavior_tree


def test_build_task_behavior_tree_reads_declared_yaml_spec() -> None:
    tree = build_task_behavior_tree()
    assert tree.root.label == 'pick_place_root'


def test_build_task_behavior_tree_fails_closed_on_cycle(tmp_path: Path) -> None:
    spec = tmp_path / 'cycle.yaml'
    spec.write_text(
        """version: 1
root: loop
nodes:
  loop:
    type: sequence
    children: [loop]
""",
        encoding='utf-8',
    )
    with pytest.raises(RuntimeError, match='contains a cycle'):
        build_task_behavior_tree(spec)


def test_build_task_behavior_tree_fails_closed_on_missing_action_event(tmp_path: Path) -> None:
    spec = tmp_path / 'invalid.yaml'
    spec.write_text(
        """version: 1
root: root
nodes:
  root:
    type: sequence
    children: [broken]
  broken:
    type: action
""",
        encoding='utf-8',
    )
    with pytest.raises(RuntimeError, match='missing required event field'):
        build_task_behavior_tree(spec)
