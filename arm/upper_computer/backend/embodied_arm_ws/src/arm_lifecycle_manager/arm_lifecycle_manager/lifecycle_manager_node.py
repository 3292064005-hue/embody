from __future__ import annotations

import json
import warnings
import time

import rclpy
from rclpy.node import Node
from std_msgs.msg import String

from arm_common import MsgTypes, TopicNames, parse_calibration_profile_message

CalibrationProfileMsg = MsgTypes.CalibrationProfileMsg
HardwareState = MsgTypes.HardwareState
SystemState = MsgTypes.SystemState


class LifecycleManagerNode(Node):
    def __init__(self) -> None:
        super().__init__("lifecycle_manager_node")
        self._hardware = None
        self._system = None
        self._calibration = None
        self._profiles = None
        self._pub = self.create_publisher(String, TopicNames.BRINGUP_STATUS, 10)
        self.create_subscription(HardwareState, TopicNames.HARDWARE_STATE, self._on_hardware, 20)
        self.create_subscription(SystemState, TopicNames.SYSTEM_STATE, self._on_system, 20)
        self.create_subscription(String, TopicNames.CALIBRATION_PROFILE, self._on_calibration, 10)
        if CalibrationProfileMsg is not object:
            self.create_subscription(CalibrationProfileMsg, TopicNames.CALIBRATION_PROFILE_TYPED, self._on_calibration_typed, 10)
        self.create_subscription(String, TopicNames.PROFILES_ACTIVE, self._on_profiles, 10)
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

    def _publish(self) -> None:
        payload = {
            "stamp_monotonic": time.monotonic(),
            "calibration_loaded": bool(self._calibration),
            "profiles_loaded": bool(self._profiles),
            "hardware_seen": self._hardware is not None,
            "system_seen": self._system is not None,
            "ready": bool(
                self._hardware is not None
                and self._system is not None
                and self._calibration
                and self._profiles
            ),
        }
        self._pub.publish(String(data=json.dumps(payload, ensure_ascii=False)))


def main(args=None) -> None:
    warnings.warn('This node is deprecated. Use the split-stack replacement packages instead.', DeprecationWarning, stacklevel=2)
    rclpy.init(args=args)
    node = LifecycleManagerNode()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()
