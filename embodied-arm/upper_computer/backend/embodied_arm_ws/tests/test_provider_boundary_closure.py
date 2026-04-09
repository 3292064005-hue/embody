from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / 'src'


def test_motion_planner_provider_module_uses_pure_services_instead_of_runtime_nodes() -> None:
    text = (ROOT / 'arm_motion_planner' / 'arm_motion_planner' / 'providers.py').read_text(encoding='utf-8')
    assert 'SceneService' in text
    assert 'GraspPlanningService' in text
    assert 'SceneManagerNode(' not in text
    assert 'GraspPlannerNode(' not in text


def test_scene_and_grasp_nodes_delegate_to_service_layers() -> None:
    scene_text = (ROOT / 'arm_scene_manager' / 'arm_scene_manager' / 'scene_manager_node.py').read_text(encoding='utf-8')
    grasp_text = (ROOT / 'arm_grasp_planner' / 'arm_grasp_planner' / 'grasp_planner_node.py').read_text(encoding='utf-8')
    assert 'SceneService' in scene_text
    assert 'GraspPlanningService' in grasp_text
