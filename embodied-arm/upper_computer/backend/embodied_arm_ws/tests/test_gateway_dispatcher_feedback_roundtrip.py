from __future__ import annotations

import shutil
import threading
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]


def _require_ros_runtime() -> None:
    if shutil.which('ros2') is None or shutil.which('colcon') is None:
        pytest.skip('ROS2 / colcon runtime unavailable in this environment')


class _RosRuntimeHarness:
    def __init__(self) -> None:
        _require_ros_runtime()
        import rclpy
        from rclpy.executors import MultiThreadedExecutor

        from gateway.state import GatewayState
        from gateway.ros_bridge import GatewayRosNode
        from arm_hardware_bridge.hardware_command_dispatcher_node import HardwareCommandDispatcherNode
        from arm_hardware_bridge.hardware_state_aggregator_node import HardwareStateAggregatorNode
        from arm_hardware_bridge.stm32_serial_node import Stm32SerialNode

        self.rclpy = rclpy
        self.MultiThreadedExecutor = MultiThreadedExecutor
        self.GatewayState = GatewayState
        self.GatewayRosNode = GatewayRosNode
        self.HardwareCommandDispatcherNode = HardwareCommandDispatcherNode
        self.HardwareStateAggregatorNode = HardwareStateAggregatorNode
        self.Stm32SerialNode = Stm32SerialNode
        self.events: list[tuple[str, object]] = []

    def __enter__(self):
        self.rclpy.init(args=None)
        self.state = self.GatewayState()
        self.gateway = self.GatewayRosNode(self.state, lambda event, payload: self.events.append((event, payload)))
        self.dispatcher = self.HardwareCommandDispatcherNode()
        self.aggregator = self.HardwareStateAggregatorNode()
        self.stm32 = self.Stm32SerialNode()
        self.executor = self.MultiThreadedExecutor()
        for node in (self.gateway, self.dispatcher, self.aggregator, self.stm32):
            self.executor.add_node(node)
        self.thread = threading.Thread(target=self.executor.spin, daemon=True)
        self.thread.start()
        time.sleep(0.5)
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.executor.shutdown()
        for node in (self.gateway, self.dispatcher, self.aggregator, self.stm32):
            try:
                node.destroy_node()
            except Exception:
                pass
        if self.rclpy.ok():
            self.rclpy.shutdown()
        self.thread.join(timeout=2.0)


def _wait_for(predicate, timeout: float = 6.0, step: float = 0.05) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(step)
    return False


def test_gateway_dispatcher_feedback_roundtrip_updates_gateway_hardware_state() -> None:
    with _RosRuntimeHarness() as harness:
        harness.gateway.publish_hardware_command({
            'kind': 'SERVO_CARTESIAN',
            'task_id': 'pytest-roundtrip',
            'axis': 'x',
            'delta': 0.02,
            'timeout_sec': 0.4,
        })

        def _roundtrip_complete() -> bool:
            hardware = harness.state.get_hardware()
            raw = hardware.get('rawStatus') or {}
            dispatcher = raw.get('dispatcher') or {}
            joints = hardware.get('joints') or []
            return bool(
                hardware.get('sourceStm32Online')
                and raw.get('last_kind') == 'SERVO_CARTESIAN'
                and dispatcher.get('ack', 0) >= 1
                and dispatcher.get('done', 0) >= 1
                and joints
                and abs(float(joints[0])) > 0.0
            )

        assert _wait_for(_roundtrip_complete), harness.state.get_hardware()
        hardware = harness.state.get_hardware()
        raw = hardware.get('rawStatus') or {}
        dispatcher = raw.get('dispatcher') or {}
        assert hardware['sourceStm32Online'] is True
        assert raw.get('last_kind') == 'SERVO_CARTESIAN'
        assert dispatcher['ack'] >= 1
        assert dispatcher['done'] >= 1
        assert any(event == 'hardware.state.updated' for event, _ in harness.events)


def test_gateway_dispatcher_feedback_roundtrip_unexpected_servo_axis_falls_back_without_crash() -> None:
    with _RosRuntimeHarness() as harness:
        baseline = list(harness.state.get_hardware().get('joints') or [])
        harness.gateway.publish_hardware_command({
            'kind': 'SERVO_CARTESIAN',
            'task_id': 'pytest-roundtrip-invalid-axis',
            'axis': 'unknown-axis',
            'delta': 0.01,
            'timeout_sec': 0.4,
        })

        def _roundtrip_complete() -> bool:
            hardware = harness.state.get_hardware()
            raw = hardware.get('rawStatus') or {}
            dispatcher = raw.get('dispatcher') or {}
            joints = hardware.get('joints') or []
            return bool(
                raw.get('last_kind') == 'SERVO_CARTESIAN'
                and dispatcher.get('ack', 0) >= 1
                and dispatcher.get('done', 0) >= 1
                and joints
            )

        assert _wait_for(_roundtrip_complete), harness.state.get_hardware()
        hardware = harness.state.get_hardware()
        joints = hardware.get('joints') or []
        raw_kind = (hardware.get('rawStatus') or {}).get('last_kind')
        assert raw_kind == 'SERVO_CARTESIAN'
        assert joints
        if baseline:
            assert float(joints[0]) != float(baseline[0])


def test_gateway_dispatcher_feedback_roundtrip_set_joints_joint_stream_updates_gateway_hardware_state() -> None:
    with _RosRuntimeHarness() as harness:
        harness.gateway.publish_hardware_command({
            'kind': 'SET_JOINTS',
            'task_id': 'pytest-set-joints',
            'producer': 'ros2_control_backbone',
            'command_plane': 'joint_stream',
            'joint_names': ['joint_1', 'joint_2'],
            'joint_positions': [0.15, -0.05],
            'gripper_position': 0.04,
            'timeout_sec': 0.4,
        })

        def _roundtrip_complete() -> bool:
            hardware = harness.state.get_hardware()
            raw = hardware.get('rawStatus') or {}
            dispatcher = raw.get('dispatcher') or {}
            joints = hardware.get('joints') or []
            return bool(
                raw.get('last_kind') == 'SET_JOINTS'
                and dispatcher.get('ack', 0) >= 1
                and dispatcher.get('done', 0) >= 1
                and len(joints) >= 2
                and abs(float(joints[0]) - 0.15) < 1e-6
                and abs(float(joints[1]) + 0.05) < 1e-6
            )

        assert _wait_for(_roundtrip_complete), harness.state.get_hardware()
