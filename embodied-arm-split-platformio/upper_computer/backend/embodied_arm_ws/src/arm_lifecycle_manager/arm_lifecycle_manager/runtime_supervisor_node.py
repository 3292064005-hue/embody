from __future__ import annotations

import json
import time

import rclpy
from rclpy.node import Node
from std_msgs.msg import String

from arm_common import MsgTypes, TopicNames, build_bringup_status_message, parse_calibration_profile_message

from .bringup_status import build_runtime_supervisor_status_payload

BringupStatus = MsgTypes.BringupStatus
CalibrationProfileMsg = MsgTypes.CalibrationProfileMsg
HardwareState = MsgTypes.HardwareState
SystemState = MsgTypes.SystemState


class RuntimeSupervisorNode(Node):
    """Lightweight runtime supervisor for bringup sequencing visibility."""

    def __init__(self) -> None:
        super().__init__('runtime_supervisor_node')
        self.declare_parameter('required_nodes', [
            'arm_profiles',
            'arm_calibration',
            'arm_hardware_bridge',
            'arm_readiness_manager',
            'arm_camera_driver',
            'arm_perception',
            'arm_motion_planner',
            'arm_motion_executor',
            'arm_task_orchestrator',
        ])
        self._hardware = None
        self._system = None
        self._calibration = None
        self._profiles = None
        self._readiness = None
        self._pub = self.create_publisher(String, TopicNames.BRINGUP_STATUS, 10)
        self._typed_pub = self.create_publisher(BringupStatus, TopicNames.BRINGUP_STATUS_TYPED, 10) if BringupStatus is not object else None
        self.create_subscription(HardwareState, TopicNames.HARDWARE_STATE, self._on_hardware, 20)
        self.create_subscription(SystemState, TopicNames.SYSTEM_STATE, self._on_system, 20)
        self.create_subscription(String, TopicNames.CALIBRATION_PROFILE, self._on_calibration, 10)
        if CalibrationProfileMsg is not object:
            self.create_subscription(CalibrationProfileMsg, TopicNames.CALIBRATION_PROFILE_TYPED, self._on_calibration_typed, 10)
        self.create_subscription(String, TopicNames.PROFILES_ACTIVE, self._on_profiles, 10)
        self.create_subscription(String, TopicNames.READINESS_UPDATE, self._on_readiness, 10)
        self.create_timer(0.5, self._publish)

    def _on_hardware(self, msg: HardwareState) -> None:
        self._hardware = msg

    def _on_system(self, msg: SystemState) -> None:
        self._system = msg

    def _on_calibration(self, msg: String) -> None:
        self._calibration = msg.data

    def _on_calibration_typed(self, msg: CalibrationProfileMsg) -> None:
        self._calibration = json.dumps(parse_calibration_profile_message(msg), ensure_ascii=False)

    def _on_profiles(self, msg: String) -> None:
        self._profiles = msg.data

    def _on_readiness(self, msg: String) -> None:
        self._readiness = msg.data

    def _payload(self) -> dict:
        mode = None if self._system is None else int(getattr(self._system, 'system_mode', 0))
        return build_runtime_supervisor_status_payload(
            stamp_monotonic=time.monotonic(),
            required_nodes=list(self.get_parameter('required_nodes').value),
            hardware_seen=self._hardware is not None,
            system_seen=self._system is not None,
            calibration_loaded=bool(self._calibration),
            profiles_loaded=bool(self._profiles),
            readiness_streaming=bool(self._readiness),
            system_mode=mode,
        )

    def _publish(self) -> None:
        payload = self._payload()
        self._pub.publish(String(data=json.dumps(payload, ensure_ascii=False)))
        if self._typed_pub is not None:
            self._typed_pub.publish(build_bringup_status_message(payload))


def main(args=None) -> None:
    rclpy.init(args=args)
    node = RuntimeSupervisorNode()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()
