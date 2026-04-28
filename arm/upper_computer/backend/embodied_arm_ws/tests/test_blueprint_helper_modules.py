from arm_calibration import CalibrationManager, CalibrationValidator, HandEyeOffsetSolver, IntrinsicsCalibrator, WorkspaceMapper
from arm_task_orchestrator import TaskQueue, EventBus, RetryPolicy, RecoveryPolicy, TaskProfileLoader, PickPlacePipeline, ClearTablePipeline
from arm_safety_supervisor import EStopMonitor, TimeoutGuard, WorkspaceGuard, CommLossGuard, FaultLatcher
from arm_logger import EventRecorder, ImageSnapshotter, TaskRecordWriter, BagTrigger, LogRotator
from arm_diagnostics import HealthMetrics, LatencyMonitor, FPSMonitor, SerialRTTMonitor, DashboardExporter
from pathlib import Path
import tempfile


def test_blueprint_helper_modules_behave_reasonably():
    mgr = CalibrationManager()
    model = mgr.load_from_dict({'version': 'v1', 'x_bias': 0.1, 'y_bias': -0.1})
    assert model.x_bias == 0.1
    assert CalibrationValidator().validate(0.2, 0.3, 1.0, 1.0)['ok']
    assert HandEyeOffsetSolver().solve([])['yaw_bias'] == 0.0
    assert IntrinsicsCalibrator().calibrate([1, 2]).frame_count == 2
    assert WorkspaceMapper(0.1, -0.2).project_pixel_to_world(1.0, 2.0) == {'x': 1.1, 'y': 1.8}

    queue = TaskQueue(capacity=1)
    assert queue.push('a')
    assert not queue.push('b')
    assert queue.pop() == 'a'
    assert EventBus().publish('evt', {'a': 1})['event_type'] == 'evt'
    assert RetryPolicy(1, 2).allow(0, 1)
    assert not RetryPolicy(1, 2).allow(1, 1)
    assert RecoveryPolicy().decide(3)['action'] == 'recover'
    assert PickPlacePipeline().build('t1')[0]['stage'] == 'PERCEPTION'
    assert ClearTablePipeline().build(['a', 'b'])[1]['target_id'] == 'b'

    assert EStopMonitor().triggered({'estop_pressed': True})
    assert TimeoutGuard().expired(0.0, 1.1, 1.0)
    assert WorkspaceGuard().within(0.1, 0.1, 1.0)
    assert CommLossGuard().lost(0.0, 2.0, 1.0)
    latcher = FaultLatcher(); latcher.latch(9); assert latcher.last_fault_code == 9; latcher.clear(); assert latcher.last_fault_code == 0

    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        recorder = EventRecorder(td / 'events.jsonl')
        recorder.append({'k': 'v'})
        assert (td / 'events.jsonl').exists()
        snapshotter = ImageSnapshotter(td / 'img')
        assert snapshotter.save_bytes('a.bin', b'123').exists()
        writer = TaskRecordWriter(td / 'tasks')
        assert writer.write('t1', {'ok': True}).exists()
        assert BagTrigger().should_record(True, False)
        assert LogRotator().rotate(td, 10)

    assert HealthMetrics().summarize(30, 12, 5)['fps'] == 30.0
    assert LatencyMonitor().measure(1.0, 1.1) > 99.0
    assert FPSMonitor().compute(10, 2.0) == 5.0
    assert SerialRTTMonitor().compute(1.0, 1.05) > 49.0
    assert DashboardExporter().export({'a': 1}).startswith('{')
