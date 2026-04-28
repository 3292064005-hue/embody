from arm_motion_executor.executor import MotionExecutor
from arm_motion_planner.planner import StagePlan


def _build_plan():
    return [
        StagePlan('move_to_pregrasp', 'connector', {'x': 0.1, 'y': 0.0, 'z': 0.1, 'yaw': 0.0, 'timeoutSec': 1.0}),
        StagePlan('descend', 'propagator', {'x': 0.1, 'y': 0.0, 'z': 0.05, 'yaw': 0.0, 'timeoutSec': 1.0}),
        StagePlan('close_gripper', 'gripper', {'open': False, 'timeoutSec': 1.0}),
        StagePlan('lift', 'propagator', {'x': 0.1, 'y': 0.0, 'z': 0.1, 'yaw': 0.0, 'timeoutSec': 1.0}),
        StagePlan('move_to_place', 'connector', {'x': 0.2, 'y': 0.1, 'z': 0.05, 'yaw': 0.0, 'timeoutSec': 1.0}),
        StagePlan('open_gripper', 'gripper', {'open': True, 'timeoutSec': 1.0}),
        StagePlan('retreat', 'propagator', {'x': 0.2, 'y': 0.1, 'z': 0.1, 'yaw': 0.0, 'timeoutSec': 1.0}),
        StagePlan('go_home', 'connector', {'named_pose': 'home', 'timeoutSec': 1.0}),
    ]


def test_motion_executor_correlates_feedback_and_timeouts():
    executor = MotionExecutor()
    plan = _build_plan()
    assert executor.validate(plan).accepted
    commands = executor.build_command_stream(plan, 'task-1')
    handle = executor.dispatch_stage(commands[0], started_monotonic=1.0)
    result = executor.accept_feedback({'command_id': handle.command_id, 'status': 'done', 'source': 'hardware', 'message': 'ok'})
    assert result.accepted is True
    assert result.status == 'done'
    timeout = executor.mark_timeout(commands[1]['command_id'])
    assert timeout.status == 'timeout'
    canceled = executor.cancel(commands[2]['command_id'])
    assert canceled.status == 'canceled'
