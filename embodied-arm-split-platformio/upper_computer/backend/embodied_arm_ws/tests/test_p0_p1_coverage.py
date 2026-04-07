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
        include_count = sum(1 for item in desc if item.__class__.__name__ == '_Record' and not getattr(item, 'kwargs', {}).get('package'))
        packages = [getattr(item, 'kwargs', {}).get('package') for item in desc if getattr(item, 'kwargs', {}).get('package')]
        assert include_count >= 2
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
