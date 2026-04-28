from __future__ import annotations

import json
import time

import rclpy
from rclpy.node import Node
from std_msgs.msg import String

from arm_common import MsgTypes, TopicNames, build_bringup_status_message, parse_calibration_profile_message

from .bringup_status import build_runtime_supervisor_status_payload

BringupStatus = MsgTypes.BringupStatus
HardwareState = MsgTypes.HardwareState
SystemState = MsgTypes.SystemState
CalibrationProfileMsg = MsgTypes.CalibrationProfileMsg


class RuntimeSupervisorNode(Node):
    """Monitor runtime-input freshness for bringup supervision.

    The supervisor intentionally separates *presence* from *freshness*: a topic
    that was observed once no longer keeps the runtime healthy forever. Inputs
    must continue refreshing within ``stale_after_sec`` to keep the bringup gate
    open. This makes disconnects and stalled publishers visible to the HMI and to
    deployment smoke tests without requiring a full ROS lifecycle stack.
    """

    def __init__(self) -> None:
        super().__init__('runtime_supervisor_node')
        self.declare_parameter(
            'required_nodes',
            [
                'profile_manager_node',
                'calibration_manager_node',
                'hardware_state_aggregator_node',
                'readiness_manager',
            ],
        )
        self.declare_parameter('stale_after_sec', 3.0)
        self.declare_parameter('publish_period_sec', 0.5)
        self._stale_after_sec = max(0.1, float(self.get_parameter('stale_after_sec').value))
        self._pub = self.create_publisher(String, TopicNames.BRINGUP_STATUS, 10)
        self._typed_pub = self.create_publisher(BringupStatus, TopicNames.BRINGUP_STATUS_TYPED, 10) if BringupStatus is not object else None
        self._hardware = None
        self._system = None
        self._calibration = ''
        self._profiles = ''
        self._readiness = ''
        self._hardware_seen_at: float | None = None
        self._system_seen_at: float | None = None
        self._calibration_seen_at: float | None = None
        self._profiles_seen_at: float | None = None
        self._readiness_seen_at: float | None = None
        self.create_subscription(HardwareState, TopicNames.HARDWARE_STATE, self._on_hardware, 20)
        self.create_subscription(SystemState, TopicNames.SYSTEM_STATE, self._on_system, 20)
        self.create_subscription(String, TopicNames.CALIBRATION_PROFILE, self._on_calibration, 10)
        if CalibrationProfileMsg is not object:
            self.create_subscription(CalibrationProfileMsg, TopicNames.CALIBRATION_PROFILE_TYPED, self._on_calibration_typed, 10)
        self.create_subscription(String, TopicNames.PROFILES_ACTIVE, self._on_profiles, 10)
        self.create_subscription(String, TopicNames.READINESS_UPDATE, self._on_readiness, 10)
        self.create_timer(float(self.get_parameter('publish_period_sec').value), self._publish)

    def _mark_seen(self, attr_name: str) -> None:
        setattr(self, attr_name, time.monotonic())

    def _on_hardware(self, msg: HardwareState) -> None:
        self._hardware = msg
        self._mark_seen('_hardware_seen_at')

    def _on_system(self, msg: SystemState) -> None:
        self._system = msg
        self._mark_seen('_system_seen_at')

    def _on_calibration(self, msg: String) -> None:
        self._calibration = msg.data
        self._mark_seen('_calibration_seen_at')

    def _on_calibration_typed(self, msg: CalibrationProfileMsg) -> None:
        self._calibration = json.dumps(parse_calibration_profile_message(msg), ensure_ascii=False)
        self._mark_seen('_calibration_seen_at')

    def _on_profiles(self, msg: String) -> None:
        self._profiles = msg.data
        self._mark_seen('_profiles_seen_at')

    def _on_readiness(self, msg: String) -> None:
        self._readiness = msg.data
        self._mark_seen('_readiness_seen_at')

    def _age_and_freshness(self, seen_at: float | None) -> tuple[float | None, bool]:
        """Return input age and whether it is still considered fresh.

        Args:
            seen_at: Monotonic timestamp of the last observed input.

        Returns:
            tuple[float | None, bool]: ``(age_sec, is_fresh)``. Missing inputs
            return ``(None, False)``.

        Raises:
            Does not raise.
        """
        if seen_at is None:
            return None, False
        age = max(0.0, time.monotonic() - float(seen_at))
        return age, age <= self._stale_after_sec

    def _payload(self) -> dict:
        mode = None if self._system is None else int(getattr(self._system, 'system_mode', 0))
        hardware_age, hardware_fresh = self._age_and_freshness(self._hardware_seen_at)
        system_age, system_fresh = self._age_and_freshness(self._system_seen_at)
        calibration_age, calibration_fresh = self._age_and_freshness(self._calibration_seen_at)
        profiles_age, profiles_fresh = self._age_and_freshness(self._profiles_seen_at)
        readiness_age, readiness_fresh = self._age_and_freshness(self._readiness_seen_at)
        return build_runtime_supervisor_status_payload(
            stamp_monotonic=time.monotonic(),
            required_nodes=list(self.get_parameter('required_nodes').value),
            hardware_seen=self._hardware is not None,
            system_seen=self._system is not None,
            calibration_loaded=bool(self._calibration),
            profiles_loaded=bool(self._profiles),
            readiness_streaming=bool(self._readiness),
            system_mode=mode,
            hardware_fresh=hardware_fresh,
            system_fresh=system_fresh,
            calibration_fresh=calibration_fresh,
            profiles_fresh=profiles_fresh,
            readiness_fresh=readiness_fresh,
            hardware_age_sec=hardware_age,
            system_age_sec=system_age,
            calibration_age_sec=calibration_age,
            profiles_age_sec=profiles_age,
            readiness_age_sec=readiness_age,
            stale_after_sec=self._stale_after_sec,
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
