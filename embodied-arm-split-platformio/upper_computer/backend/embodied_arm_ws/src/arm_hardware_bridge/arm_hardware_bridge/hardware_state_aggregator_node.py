from __future__ import annotations

import json
import time

import rclpy
from arm_backend_common.lifecycle_support import ManagedLifecycleNode, lifecycle_main
from std_msgs.msg import String

from arm_backend_common.protocol import decode_hex_frame, decode_payload
from arm_common import MsgTypes, TopicNames

HardwareState = MsgTypes.HardwareState
from .semantic_state import HardwareSemanticState


class HardwareStateAggregatorNode(ManagedLifecycleNode):
    """Aggregate raw transport signals into one semantic hardware snapshot."""

    def __init__(self) -> None:
        super().__init__('hardware_state_aggregator_node')
        self.declare_parameter('state_stale_sec', 1.0)
        self._stm32_link = {'online': False, 'expired': True, 'transportMode': 'unavailable', 'authoritative': False, 'simulatedFallback': False}
        self._esp32_link = {'online': False}
        self._dispatcher = {'pending': 0, 'sent': 0, 'ack': 0, 'nack': 0, 'retry': 0, 'timeout': 0, 'done': 0, 'fault': 0, 'parser_error': 0}
        self._state = HardwareSemanticState()
        self._last_state_update = 0.0
        self._pub = self.create_managed_publisher(HardwareState, TopicNames.HARDWARE_STATE, 20)
        self._summary_pub = self.create_managed_publisher(String, TopicNames.HARDWARE_SUMMARY, 10)
        self.create_subscription(String, TopicNames.HARDWARE_STM32_LINK, self._on_stm32_link, 20)
        self.create_subscription(String, TopicNames.HARDWARE_ESP32_LINK, self._on_esp32_link, 20)
        self.create_subscription(String, TopicNames.HARDWARE_DISPATCHER_STATE, self._on_dispatcher_state, 20)
        self.create_subscription(String, TopicNames.HARDWARE_STM32_RX, self._on_stm32_rx, 50)
        self.create_timer(0.1, self._publish_state)

    def _on_stm32_link(self, msg: String) -> None:
        try:
            self._stm32_link = json.loads(msg.data)
        except Exception:
            self._stm32_link = {'online': False, 'expired': True, 'transportMode': 'unavailable', 'authoritative': False, 'simulatedFallback': False}

    def _on_esp32_link(self, msg: String) -> None:
        try:
            self._esp32_link = json.loads(msg.data)
        except Exception:
            self._esp32_link = {'online': False}

    def _on_dispatcher_state(self, msg: String) -> None:
        try:
            self._dispatcher = json.loads(msg.data)
        except Exception:
            pass

    def _on_stm32_rx(self, msg: String) -> None:
        try:
            frame = decode_hex_frame(msg.data)
            payload = decode_payload(frame.payload)
        except Exception:
            return
        if frame.command in (0x0C, 0x0D):
            self._state.apply_report(payload)
            self._last_state_update = time.monotonic()

    def _publish_state(self) -> None:
        if not self.runtime_active:
            return
        now = time.monotonic()
        stale_age = 0.0 if self._last_state_update == 0.0 else now - self._last_state_update
        state_stale_sec = float(self.get_parameter('state_stale_sec').value)
        transport_mode = str(self._stm32_link.get('transportMode', 'real' if self._stm32_link.get('online') else 'unavailable'))
        authoritative = bool(self._stm32_link.get('authoritative', False))
        simulated_transport = transport_mode == 'simulated'
        state_stale = stale_age > state_stale_sec if self._last_state_update > 0 else True
        hardware_present = bool(self._stm32_link.get('online'))
        hardware_controllable = hardware_present and not bool(self._stm32_link.get('expired', False)) and not state_stale and authoritative
        state = HardwareState()
        state.header.stamp = self.get_clock().now().to_msg()
        state.stm32_online = hardware_present
        state.esp32_online = bool(self._esp32_link.get('online'))
        state.estop_pressed = self._state.estop_pressed
        state.home_ok = self._state.home_ok
        state.gripper_ok = self._state.gripper_ok
        state.motion_busy = self._state.motion_busy
        state.limit_triggered = self._state.limit_triggered
        state.joint_position = self._state.joint_position
        state.joint_velocity = self._state.joint_velocity
        state.hardware_fault_code = self._state.hardware_fault_code
        state.raw_status = json.dumps(
            {
                **self._state.to_dict(),
                'stm32_link': self._stm32_link,
                'esp32_link': self._esp32_link,
                'dispatcher': self._dispatcher,
                'last_state_age_sec': stale_age,
                'state_stale': state_stale,
                'transportMode': transport_mode,
                'online': hardware_present,
                'authoritative': authoritative,
                'controllable': hardware_controllable,
                'hardwarePresent': hardware_present,
                'hardwareAuthoritative': authoritative,
                'hardwareControllable': hardware_controllable,
                'simulatedTransport': simulated_transport,
                'simulatedFallback': bool(self._stm32_link.get('simulatedFallback', False)),
                'connectionError': self._stm32_link.get('connectionError'),
            },
            ensure_ascii=False,
        )
        self._pub.publish(state)
        self._summary_pub.publish(String(data=state.raw_status))



def main(args=None) -> None:
    lifecycle_main(HardwareStateAggregatorNode, args=args)
