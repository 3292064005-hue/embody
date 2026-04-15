from __future__ import annotations

from arm_motion_planner.backend_factory import resolve_planning_backend
from arm_motion_planner.moveit_client import PlanningRequest


def _backend():
    resolved = resolve_planning_backend(
        capability_mode='validated_live',
        backend_name='validated_live_bridge',
        backend_profile='validated_live_bridge',
    )
    assert resolved.backend is not None
    return resolved.backend


def _metadata(*, object_x: float = 0.1, object_y: float = 0.12, object_z: float = 0.03, object_yaw: float = 0.1) -> dict[str, object]:
    return {
        'sceneSnapshot': {
            'sceneAvailable': True,
            'providerMode': 'runtime_service',
            'providerAuthoritative': True,
            'snapshotId': 'scene-1',
            'staticScene': {
                'objects': [
                    {
                        'id': 'table',
                        'pose': {'x': 0.0, 'y': 0.0, 'z': -0.01},
                        'dimensions': {'x': 0.6, 'y': 0.4, 'z': 0.02},
                    }
                ]
            },
            'targetCollisionObject': {
                'id': 'target-1',
                'pose': {'x': object_x, 'y': object_y, 'z': object_z, 'yaw': object_yaw},
                'dimensions': {'x': 0.04, 'y': 0.04, 'z': 0.06},
            },
            'attachments': [],
        },
        'sceneProviderMode': 'runtime_service',
        'sceneProviderAuthoritative': True,
        'graspCandidate': {
            'candidate_id': 'target-1:candidate-1',
            'grasp_x': object_x,
            'grasp_y': object_y,
            'yaw': object_yaw,
        },
        'graspProviderMode': 'runtime_service',
        'graspProviderAuthoritative': True,
    }


def test_validated_live_backend_rejects_missing_runtime_service_scene_and_grasp_metadata() -> None:
    backend = _backend()
    request = PlanningRequest(
        request_kind='pose_goal',
        frame='table',
        target={'x': 0.1, 'y': 0.1, 'z': 0.12, 'yaw': 0.0},
        metadata={},
    )
    result = backend(request)
    assert result.success is False
    assert 'sceneSnapshot runtime metadata' in result.error_message


def test_validated_live_backend_accepts_authoritative_runtime_service_metadata() -> None:
    backend = _backend()
    request = PlanningRequest(
        request_kind='pose_goal',
        frame='table',
        target={'x': 0.1, 'y': 0.12, 'z': 0.14, 'yaw': 0.1},
        metadata=_metadata(),
    )
    result = backend(request)
    assert result.success is True
    assert result.authoritative is True
    assert result.metadata['planningModel'] == 'authoritative_live_kinematic_scene_planner_v1'
    diagnostics = dict(result.trajectory['planningDiagnostics'])
    assert diagnostics['jointSolutionMode'] == 'analytic_inverse_kinematics'
    goal = next(item for item in diagnostics['waypointDiagnostics'] if item['phase'] == 'goal')
    achieved = dict(goal['achievedPose'])
    assert abs(float(achieved['x']) - 0.1) < 1e-3
    assert abs(float(achieved['y']) - 0.12) < 1e-3
    assert abs(float(achieved['z']) - 0.14) < 1e-3
    arm_target = result.trajectory['controllerTargets']['arm']
    assert arm_target['joint_names']
    assert len(arm_target['points']) >= 3


def test_validated_live_backend_rejects_target_collision_violation() -> None:
    backend = _backend()
    request = PlanningRequest(
        request_kind='pose_goal',
        frame='table',
        target={'x': 0.1, 'y': 0.12, 'z': 0.04, 'yaw': 0.1},
        metadata=_metadata(),
    )
    result = backend(request)
    assert result.success is False
    assert 'target top clearance' in result.error_message


def test_validated_live_backend_rejects_named_pose_without_authoritative_scene_metadata() -> None:
    backend = _backend()
    request = PlanningRequest(
        request_kind='named_pose',
        frame='base_link',
        target={'named_pose': 'home'},
        metadata={},
    )
    result = backend(request)
    assert result.success is False
    assert 'sceneSnapshot runtime metadata' in result.error_message


def test_validated_live_backend_accepts_named_pose_with_authoritative_scene_metadata() -> None:
    backend = _backend()
    request = PlanningRequest(
        request_kind='named_pose',
        frame='base_link',
        target={'named_pose': 'home'},
        metadata=_metadata(),
    )
    result = backend(request)
    assert result.success is True
    diagnostics = dict(result.trajectory['planningDiagnostics'])
    assert diagnostics['jointSolutionMode'] == 'named_pose_profile'
    assert diagnostics['sceneValidationMode'] == 'authoritative_named_pose_scene_guard'


def test_validated_live_backend_rejects_static_scene_obstacle_collision() -> None:
    backend = _backend()
    metadata = _metadata()
    metadata['sceneSnapshot']['staticScene']['objects'].append(
        {
            'id': 'obstacle-1',
            'pose': {'x': 0.1, 'y': 0.12, 'z': 0.14},
            'dimensions': {'x': 0.05, 'y': 0.05, 'z': 0.05},
        }
    )
    request = PlanningRequest(
        request_kind='pose_goal',
        frame='table',
        target={'x': 0.1, 'y': 0.12, 'z': 0.14, 'yaw': 0.1},
        metadata=metadata,
    )
    result = backend(request)
    assert result.success is False
    assert 'authoritative scene obstacle obstacle-1' in result.error_message
