from arm_motion_planner.moveit_client import MoveItClient, PlanResult, PlanningRequest, SceneState
from arm_motion_planner.planner import MotionPlanner
from arm_backend_common.data_models import CalibrationProfile, TargetSnapshot, TaskContext


def _scene_provider() -> SceneState:
    return SceneState(available=True, source='test_scene', objects=({'id': 'table'},))


def _backend(request: PlanningRequest) -> PlanResult:
    return PlanResult(accepted=True, success=True, planner_plugin='pilz', scene_source='test_scene', request_kind=request.request_kind, trajectory={'waypoints': [dict(request.target)]}, planning_time_sec=0.02, request=request)


def test_moveit_client_returns_normalized_pose_plan_result():
    client = MoveItClient(planner_plugin='pilz', scene_source='test_scene', planning_backend=_backend, scene_provider=_scene_provider)
    result = client.plan_pose_goal({'x': 0.1, 'y': 0.2, 'z': 0.3, 'yaw': 0.0}, frame='table')
    assert result.success is True
    assert result.planner_plugin == 'pilz'
    assert result.scene_source == 'test_scene'
    assert result.trajectory['waypoints'][0]['x'] == 0.1


def test_motion_planner_compiles_stage_plan_to_runtime_results():
    planner = MotionPlanner(moveit_client=MoveItClient(planning_backend=_backend, scene_provider=_scene_provider))
    target = TargetSnapshot(target_id='t1', target_type='cube', semantic_label='red', table_x=0.1, table_y=0.2, yaw=0.0, confidence=0.95)
    calibration = CalibrationProfile(place_profiles={'default': {'x': 0.2, 'y': 0.0, 'yaw': 0.0}})
    context = TaskContext(task_id='task-1', task_type='pick_place')
    plan = planner.build_pick_place_plan(context, target, calibration)
    requests = planner.compile_to_planning_requests(plan)
    results = planner.runtime_plan_results(plan)
    assert requests[0]['requestKind'] == 'pose_goal'
    assert requests[0]['sceneSnapshot']['sceneAvailable'] is True
    assert requests[0]['graspCandidate']['candidate_id'].startswith('t1:')
    assert requests[-1]['requestKind'] == 'named_pose'
    assert len(results) == 6
    assert all(result.success for result in results)
    summary = planner.summarize_plan(plan)
    assert summary['sceneObjectCount'] >= 3
    assert summary['graspCandidateCount'] == 1
