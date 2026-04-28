from arm_motion_executor.motion_executor_node import MotionExecutorNode
from arm_motion_planner.motion_planner_node import MotionPlannerNode
from arm_task_orchestrator.task_orchestrator_node import TaskOrchestratorNode


class DummyActionRequest:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


def test_planner_node_parse_json_returns_empty_dict_for_invalid_payload():
    assert MotionPlannerNode._parse_json('{invalid') == {}


def test_executor_node_parse_json_returns_empty_dict_for_invalid_payload():
    assert MotionExecutorNode._parse_json('{invalid') == {}


def test_pick_place_action_request_uses_selector_for_new_action_clients():
    task_request = TaskOrchestratorNode._build_pick_place_request_from_action(object(), DummyActionRequest(task_id='t1', target_type='red', target_id='', place_profile='bin_red', max_retry=1), task_id='t1')
    assert task_request.task_type == 'pick_place'
    assert task_request.target_selector == 'red'
    assert task_request.place_profile == 'bin_red'


def test_pick_place_action_request_keeps_backward_compat_for_legacy_clients():
    task_request = TaskOrchestratorNode._build_pick_place_request_from_action(object(), DummyActionRequest(task_id='t1', target_type='PICK_AND_PLACE', target_id='blue', place_profile='bin_blue', max_retry=1), task_id='t1')
    assert task_request.task_type == 'pick_place'
    assert task_request.target_selector == 'blue'
