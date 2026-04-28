from __future__ import annotations

from arm_motion_executor.motion_executor_node import MotionExecutorNode


class _DummyClient:
    def __init__(self, *, ready: bool = True) -> None:
        self.ready = ready
        self.calls: list[float] = []

    def wait_for_server(self, timeout_sec: float) -> bool:
        self.calls.append(float(timeout_sec))
        return self.ready


class _MissingWaitClient:
    pass


def test_ros2_control_client_ready_requires_client_instance() -> None:
    ready, detail = MotionExecutorNode._ros2_control_client_ready(None, 'arm', timeout_sec=0.1)
    assert ready is False
    assert detail == 'ros2_control_action_client_unavailable:arm'


def test_ros2_control_client_ready_requires_wait_for_server_support() -> None:
    ready, detail = MotionExecutorNode._ros2_control_client_ready(_MissingWaitClient(), 'gripper', timeout_sec=0.1)
    assert ready is False
    assert detail == 'ros2_control_wait_for_server_missing:gripper'


def test_ros2_control_runtime_ready_requires_both_controllers() -> None:
    node = MotionExecutorNode.__new__(MotionExecutorNode)
    node._transport_adapter = type('Adapter', (), {'execution_mode': 'ros2_control_live'})()
    node._ros2_control_arm_client = _DummyClient(ready=True)
    node._ros2_control_gripper_client = _DummyClient(ready=False)
    node.get_parameter = lambda name: type('Param', (), {'value': 0.05})()

    ready, detail = MotionExecutorNode._ros2_control_runtime_ready(node)

    assert ready is False
    assert detail == 'ros2_control_controller_unavailable:gripper'
    assert node._ros2_control_arm_client.calls == [0.05]
    assert node._ros2_control_gripper_client.calls == [0.05]


def test_ros2_control_runtime_ready_accepts_non_live_execution_mode() -> None:
    node = MotionExecutorNode.__new__(MotionExecutorNode)
    node._transport_adapter = type('Adapter', (), {'execution_mode': 'authoritative_simulation'})()
    node._ros2_control_arm_client = None
    node._ros2_control_gripper_client = None
    node.get_parameter = lambda name: type('Param', (), {'value': 0.0})()

    ready, detail = MotionExecutorNode._ros2_control_runtime_ready(node)

    assert ready is True
    assert detail == 'executor_ready'
