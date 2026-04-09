from arm_backend_common.data_models import TargetSnapshot
from arm_grasp_planner import GraspPlannerNode


def test_grasp_planner_generates_ranked_runtime_plan() -> None:
    node = GraspPlannerNode()
    target = TargetSnapshot(target_id='t1', target_type='cube', semantic_label='red', table_x=0.1, table_y=0.2, yaw=0.0, confidence=0.95)
    plan = node.plan(target, {'x': 0.2, 'y': 0.0, 'yaw': 0.0}, failed_ids=['t1:top_down'])
    assert plan['status'] == 'planned'
    assert plan['candidateCount'] == 3
    assert plan['candidate']['candidate_id'] != 't1:top_down'
    assert plan['place']['x'] == 0.2
    assert plan['selectedTargetKey'] == target.key()
