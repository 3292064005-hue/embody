from arm_backend_common.data_models import CalibrationProfile, TargetSnapshot, TaskContext
from arm_backend_common.stage_plan import StagePlan
from arm_common.runtime_contracts import build_execution_request, build_execution_status, build_planning_request, build_planning_result


def test_split_stack_contracts_emit_canonical_trace_envelope() -> None:
    context = TaskContext(task_id='task-1', task_type='pick_place', target_selector='red')
    target = TargetSnapshot(target_id='target-1', target_type='cube', semantic_label='red', table_x=0.1, table_y=0.0, confidence=0.99)
    calibration = CalibrationProfile()
    plan = [StagePlan('move_to_pregrasp', 'connector', {'x': 0.1, 'y': 0.0, 'z': 0.2, 'yaw': 0.0})]

    planning_request = build_planning_request(request_id='plan-req', context=context, target=target, calibration=calibration, correlation_id='corr-1', task_run_id='run-1', episode_id='episode-1')
    planning_result = build_planning_result(request_id='plan-req', task_id='task-1', accepted=True, message='ok', plan=plan, correlation_id='corr-1', task_run_id='run-1', episode_id='episode-1')
    execution_request = build_execution_request(request_id='exec-req', task_id='task-1', plan=plan, correlation_id='corr-1', task_run_id='run-1', episode_id='episode-1')
    execution_status = build_execution_status(request_id='exec-req', task_id='task-1', status='accepted', message='ok', correlation_id='corr-1', task_run_id='run-1', episode_id='episode-1')

    for payload in (planning_request, planning_result, execution_request, execution_status):
        assert payload['traceEnvelope'] == {
            'requestId': payload['requestId'],
            'taskId': 'task-1',
            'correlationId': 'corr-1',
            'taskRunId': 'run-1',
            'episodeId': 'episode-1',
        }
