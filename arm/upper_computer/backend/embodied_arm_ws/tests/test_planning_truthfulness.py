from __future__ import annotations

import json
from pathlib import Path

import pytest

from arm_motion_planner.errors import PlanningUnavailableError
from arm_motion_planner.moveit_client import MoveItClient, PlanResult, PlanningRequest, SceneState


def _scene_provider() -> SceneState:
    return SceneState(available=True, source='test_scene', objects=({'id': 'table'},))


def _authoritative_backend(request: PlanningRequest) -> PlanResult:
    return PlanResult(
        accepted=True,
        success=True,
        planner_plugin='pilz',
        scene_source='test_scene',
        request_kind=request.request_kind,
        trajectory={'waypoints': [dict(request.target)]},
        planning_time_sec=0.02,
        request=request,
        authoritative=True,
        capability_mode='validated_sim',
        backend_name='test_backend',
    )


def test_moveit_client_contract_only_results_are_non_authoritative() -> None:
    client = MoveItClient(
        planner_plugin='pilz',
        scene_source='test_scene',
        capability_mode='contract_only',
        authoritative=False,
        backend_name='fallback_contract',
        scene_provider=_scene_provider,
    )
    result = client.plan_pose_goal({'x': 0.1, 'y': 0.2, 'z': 0.3, 'yaw': 0.0}, frame='table')
    assert result.success is True
    assert result.authoritative is False
    assert result.capability_mode == 'contract_only'
    assert result.backend_name == 'fallback_contract'
    assert result.metadata['planningAuthoritative'] is False
    assert result.metadata['planningCapability'] == 'contract_only'



def test_moveit_client_disabled_mode_fails_closed() -> None:
    client = MoveItClient(
        capability_mode='disabled',
        authoritative=False,
        backend_name='disabled_backend',
        scene_provider=_scene_provider,
    )
    with pytest.raises(PlanningUnavailableError, match='planning capability disabled'):
        client.plan_pose_goal({'x': 0.0, 'y': 0.0, 'z': 0.2}, frame='table')



def test_moveit_client_validated_backend_preserves_authoritative_metadata() -> None:
    client = MoveItClient(
        planning_backend=_authoritative_backend,
        scene_provider=_scene_provider,
        capability_mode='validated_sim',
        authoritative=True,
        backend_name='test_backend',
    )
    result = client.plan_pose_goal({'x': 0.1, 'y': 0.0, 'z': 0.2}, frame='table')
    assert result.success is True
    assert result.authoritative is True
    assert result.capability_mode == 'validated_sim'
    assert result.backend_name == 'test_backend'
    assert result.metadata['planningAuthoritative'] is True
    assert result.metadata['planningCapability'] == 'validated_sim'



def test_motion_planner_node_rejects_non_authoritative_runtime_requests() -> None:
    text = (Path(__file__).resolve().parents[1] / 'src' / 'arm_motion_planner' / 'arm_motion_planner' / 'motion_planner_node.py').read_text(encoding='utf-8')
    assert 'planning capability not authoritative' in text
    assert 'planner_contract_only' in text
    assert 'planning_capability' in text
    assert 'planning_authoritative' in text
