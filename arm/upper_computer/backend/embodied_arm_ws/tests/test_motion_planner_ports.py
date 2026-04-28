from __future__ import annotations

from arm_backend_common.data_models import CalibrationProfile, TaskContext, TaskRequest
from arm_motion_planner import MotionPlanner


class _FakeSceneProvider:
    def __init__(self) -> None:
        self.payloads = []

    def sync_scene(self, payload: dict):
        self.payloads.append(dict(payload))
        return {'objectCount': 3, 'attachments': [], 'frame': 'world'}


class _FakeGraspProvider:
    def __init__(self) -> None:
        self.requests = []

    def plan(self, target: dict, place_zone: dict | None = None, *, failed_ids: list[str] | None = None):
        self.requests.append((dict(target), dict(place_zone or {}), list(failed_ids or [])))
        return {'candidate': {'grasp_x': target['table_x'], 'grasp_y': target['table_y'], 'yaw': target['yaw']}}


def test_motion_planner_uses_injected_scene_and_grasp_ports():
    scene = _FakeSceneProvider()
    grasp = _FakeGraspProvider()
    planner = MotionPlanner(scene_manager=scene, grasp_planner=grasp)
    calibration = CalibrationProfile(place_profiles={'bin_red': {'x': 0.2, 'y': 0.1, 'yaw': 0.0}})
    context = TaskContext.from_request(TaskRequest(task_id='t-1', task_type='pick_place', target_selector='red', place_profile='bin_red'))
    plan = planner.build_pick_place_plan(
        context,
        {
            'target_id': 'target-1',
            'target_type': 'cube',
            'semantic_label': 'red',
            'table_x': 0.05,
            'table_y': 0.02,
            'yaw': 0.0,
            'confidence': 0.95,
        },
        calibration,
    )
    assert len(plan) == 8
    assert scene.payloads and scene.payloads[0]['target']['target_id'] == 'target-1'
    assert grasp.requests and grasp.requests[0][0]['target_id'] == 'target-1'
