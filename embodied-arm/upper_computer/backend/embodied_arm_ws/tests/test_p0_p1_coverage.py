from __future__ import annotations

import asyncio
import importlib.util
import sys
import types
from pathlib import Path
from types import SimpleNamespace

from arm_backend_common.data_models import CalibrationProfile, TaskProfile, TaskRequest
from arm_motion_executor import MotionExecutor
from arm_motion_planner import MotionPlanner
from arm_task_orchestrator import TaskOrchestrator
from arm_task_orchestrator.task_orchestrator_node import TaskOrchestratorNode

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / 'backend' / 'embodied_arm_ws' / 'src'
LAUNCH_FACTORY = SRC / 'arm_bringup' / 'arm_bringup' / 'launch_factory.py'


def _install_launch_stubs() -> None:
    if 'launch' in sys.modules:
        return
    launch = types.ModuleType('launch')
    actions = types.ModuleType('launch.actions')
    sources = types.ModuleType('launch.launch_description_sources')
    conditions = types.ModuleType('launch.conditions')
    substitutions = types.ModuleType('launch.substitutions')
    launch_ros = types.ModuleType('launch_ros')
    ros_actions = types.ModuleType('launch_ros.actions')
    ros_substitutions = types.ModuleType('launch_ros.substitutions')

    class LaunchDescription(list):
        pass

    class _Record:
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs

    class _Node(_Record):
        pass

    launch.LaunchDescription = LaunchDescription
    actions.DeclareLaunchArgument = _Record
    actions.IncludeLaunchDescription = _Record
    sources.PythonLaunchDescriptionSource = _Record
    conditions.IfCondition = _Record
    substitutions.LaunchConfiguration = lambda name: f'cfg:{name}'
    substitutions.PathJoinSubstitution = lambda parts: '/'.join(str(item) for item in parts)
    substitutions.PythonExpression = lambda parts: ''.join(str(item) for item in parts)
    ros_actions.Node = _Node
    ros_actions.LifecycleNode = _Node
    ros_substitutions.FindPackageShare = lambda pkg: f'/opt/{pkg}'

    sys.modules['launch'] = launch
    sys.modules['launch.actions'] = actions
    sys.modules['launch.launch_description_sources'] = sources
    sys.modules['launch.conditions'] = conditions
    sys.modules['launch.substitutions'] = substitutions
    sys.modules['launch_ros'] = launch_ros
    sys.modules['launch_ros.actions'] = ros_actions
    sys.modules['launch_ros.substitutions'] = ros_substitutions


def _load_launch_factory_module():
    _install_launch_stubs()
    spec = importlib.util.spec_from_file_location('batch7_launch_factory', LAUNCH_FACTORY)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_p0_interfaces_contract_files_exist():
    interface_root = SRC / 'arm_interfaces'
    expected = [
        interface_root / 'action' / 'PickPlaceTask.action',
        interface_root / 'action' / 'Homing.action',
        interface_root / 'action' / 'Recover.action',
        interface_root / 'srv' / 'ResetFault.srv',
        interface_root / 'msg' / 'TaskStatus.msg',
    ]
    for path in expected:
        assert path.exists(), f'missing contract file: {path}'


def test_p1_launch_factory_smoke_across_modes():
    module = _load_launch_factory_module()
    for mode in ('sim', 'hybrid', 'real', 'hw', 'full_demo'):
        desc = module.build_launch_description(mode)
        assert isinstance(desc, list)
        packages = [getattr(item, 'kwargs', {}).get('package') for item in desc if getattr(item, 'kwargs', {}).get('package')]
        assert 'arm_camera_driver' in packages
        assert 'arm_perception' in packages
        assert 'arm_motion_planner' in packages
        assert 'arm_motion_executor' in packages


def test_p1_sim_pick_place_pipeline_smoke():
    calibration = CalibrationProfile(place_profiles={'bin_red': {'x': 0.2, 'y': 0.1, 'yaw': 0.0}})
    orchestrator = TaskOrchestrator(TaskProfile(confidence_threshold=0.5))
    request = TaskRequest(task_id='sim-1', task_type='pick_place', target_selector='red', place_profile='bin_red')
    context = orchestrator.begin_context(request)
    target = SimpleNamespace(target_id='t-red', target_type='cube', semantic_label='red', table_x=0.02, table_y=0.03, yaw=0.0, confidence=0.9)
    planner = MotionPlanner()
    executor = MotionExecutor()
    plan = planner.build_pick_place_plan(context, target, calibration)
    validation = executor.validate(plan)
    stream = executor.build_command_stream(plan, request.task_id)
    assert validation.accepted is True
    assert stream[0]['task_id'] == 'sim-1'
    assert stream[-1]['kind'] == 'HOME'


def test_p1_cancel_task_marks_queued_task_canceled():
    outcomes = {}
    events = []

    def mark(task_id: str, **kwargs):
        entry = dict(outcomes.get(task_id, {}))
        entry.update(kwargs)
        outcomes[task_id] = entry

    fake = SimpleNamespace(
        _queue=[TaskRequest(task_id='queued-1', task_type='pick_place')],
        _task_outcomes=outcomes,
        _mark_task_terminal=mark,
        _emit_event=lambda *args, **kwargs: events.append((args, kwargs)),
        _current=None,
    )
    TaskOrchestratorNode._cancel_task_by_id(fake, 'queued-1', 'cancel requested')
    assert outcomes['queued-1']['state'] == 'canceled'
    assert outcomes['queued-1']['result_code'] == int(0) or isinstance(outcomes['queued-1']['result_code'], int)
    assert outcomes['queued-1']['elapsed'] == 0.0
    assert events and events[0][0][2] == 'TASK_CANCELED'


class _FakeGoalHandle:
    def __init__(self, cancel: bool = False):
        self.is_cancel_requested = cancel
        self.state = None

    def canceled(self):
        self.state = 'canceled'

    def succeed(self):
        self.state = 'succeeded'


class _RecoverAction:
    class Result:
        def __init__(self):
            self.success = False
            self.final_state = ''
            self.message = ''


def test_p1_recover_action_clears_queue_and_returns_idle():
    sent = []
    fake = SimpleNamespace(
        _queue=[object(), object()],
        _send_hardware_command=lambda payload: sent.append(payload),
        _state_machine=SimpleNamespace(to_idle=lambda reason: sent.append({'idle_reason': reason})),
        _build_stateful_action_result=lambda action_type, success, final_state, message: {
            'success': success,
            'final_state': final_state,
            'message': message,
        },
    )
    goal = _FakeGoalHandle(cancel=False)
    result = asyncio.run(TaskOrchestratorNode._execute_recover_action(fake, goal))
    assert goal.state == 'succeeded'
    assert result['success'] is True
    assert result['final_state'] == 'idle'
    assert fake._queue == []
    assert any(item.get('kind') == 'RESET_FAULT' for item in sent if isinstance(item, dict))



def test_p0_authoritative_lanes_forward_hardware_commands_and_expose_execution_truthfulness():
    module = _load_launch_factory_module()
    manifest = module.runtime_lane_manifest()
    assert manifest['sim_authoritative']['forward_hardware_commands'] is True
    assert manifest['sim_authoritative']['hardware_execution_mode'] == 'authoritative_simulation'
    assert manifest['sim_authoritative']['frame_ingress_mode'] == 'synthetic_frame_stream'
    assert manifest['sim_preview']['forward_hardware_commands'] is False
    assert manifest['sim_preview']['hardware_execution_mode'] == 'protocol_bridge'


def test_p0_dispatcher_feedback_contract_includes_command_correlation_fields():
    dispatcher = (ROOT / 'backend' / 'embodied_arm_ws' / 'src' / 'arm_hardware_bridge' / 'arm_hardware_bridge' / 'hardware_command_dispatcher_node.py').read_text(encoding='utf-8')
    assert "'command_id'" in dispatcher
    assert "'plan_id'" in dispatcher
    assert "'request_id'" in dispatcher
    assert "'task_run_id'" in dispatcher
    assert "'transport_state'" in dispatcher
    assert "'transport_result'" in dispatcher
    assert "'actuation_state'" in dispatcher
    assert "'actuation_result'" in dispatcher


def test_p1_frame_ingress_and_execution_modes_are_externalized_in_runtime_profiles():
    runtime_profiles = (ROOT / 'backend' / 'embodied_arm_ws' / 'src' / 'arm_bringup' / 'config' / 'runtime_profiles.yaml').read_text(encoding='utf-8')
    assert 'frame_ingress_mode:' in runtime_profiles
    assert 'hardware_execution_mode:' in runtime_profiles
    assert 'forward_hardware_commands:' in runtime_profiles


def test_home_sequence_action_uses_transport_adapter_dispatch() -> None:
    import inspect
    from arm_motion_executor.motion_executor_node import MotionExecutorNode

    source = inspect.getsource(MotionExecutorNode._execute_home_sequence_action)
    assert '_transport_adapter.dispatch(command)' in source
    assert '_hardware_cmd_pub.publish' not in source


def test_home_sequence_action_dispatches_through_transport_adapter_runtime_behavior() -> None:
    from arm_motion_executor import motion_executor_node as motion_executor_node_module

    original_action_types = motion_executor_node_module.ActionTypes

    class _Feedback:
        def __init__(self) -> None:
            self.stage = ''
            self.progress = 0.0

    class _Result:
        def __init__(self) -> None:
            self.accepted = False
            self.message = ''

    class _HomeSequence:
        Feedback = _Feedback
        Result = _Result

    class _GoalHandle:
        def __init__(self) -> None:
            self.feedback: list[tuple[str, float]] = []
            self.state = None

        def publish_feedback(self, payload) -> None:
            self.feedback.append((payload.stage, payload.progress))

        def succeed(self) -> None:
            self.state = 'succeeded'

        def abort(self) -> None:
            self.state = 'aborted'

    dispatched: list[tuple[str, dict]] = []

    def _dispatch_stage(command: dict, *, started_monotonic: float) -> None:
        assert started_monotonic > 0.0
        dispatched.append(('stage', dict(command)))

    fake_node = SimpleNamespace(
        _executor=SimpleNamespace(dispatch_stage=_dispatch_stage),
        _controller=SimpleNamespace(send_command=lambda command: dispatched.append(('controller', dict(command)))),
        _transport_adapter=SimpleNamespace(
            dispatch=lambda command: SimpleNamespace(
                forwarded=True,
                transport_mode='dispatcher',
                execution_mode='authoritative_simulation',
                message='forwarded',
            )
        ),
        _await_terminal_execution=lambda command_id, timeout_sec: {
            'status': 'done',
            'message': 'ok',
            'feedbackSource': 'hardware_feedback',
            'stageName': 'go_home',
        },
        _last_execution={},
    )
    goal = _GoalHandle()

    try:
        motion_executor_node_module.ActionTypes = SimpleNamespace(HomeSequence=_HomeSequence)
        result = asyncio.run(motion_executor_node_module.MotionExecutorNode._execute_home_sequence_action(fake_node, goal))
    finally:
        motion_executor_node_module.ActionTypes = original_action_types

    assert result.accepted is True
    assert result.message == 'ok'
    assert goal.state == 'succeeded'
    assert dispatched[0][0] == 'stage'
    assert dispatched[1][0] == 'controller'
    assert fake_node._last_execution['status'] == 'done'
    assert fake_node._last_execution['feedbackSource'] == 'hardware_feedback'
    assert goal.feedback[0] == ('go_home', 0.5)
    assert goal.feedback[-1] == ('go_home', 1.0)
