from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass
from typing import Any, Dict, List

import rclpy
from arm_backend_common.lifecycle_support import ManagedLifecycleNode, lifecycle_main
from std_msgs.msg import String

from arm_backend_common.enums import HardwareCommand
from arm_backend_common.protocol import build_frame, decode_hex_frame, decode_payload
from arm_backend_common.watchdog import Watchdog
from arm_common import TopicNames

try:
    import serial  # type: ignore
except Exception:
    serial = None


@dataclass
class ScheduledSimFrame:
    publish_at: float
    frame_hex: str


class Stm32SerialNode(ManagedLifecycleNode):
    """Bridge the STM32 transport while preserving fail-closed runtime semantics."""

    def __init__(self) -> None:
        super().__init__('stm32_serial_node')
        self.declare_parameter('port', '/dev/ttyUSB0')
        self.declare_parameter('baudrate', 115200)
        self.declare_parameter('heartbeat_timeout', 1.0)
        self.declare_parameter('simulate_hardware', False)
        self.declare_parameter('allow_simulation_fallback', False)
        self.declare_parameter('authoritative_simulation', False)
        self.declare_parameter('execution_mode', 'protocol_bridge')
        self.declare_parameter('sim_report_period_sec', 0.5)
        self._port = self.get_parameter('port').get_parameter_value().string_value
        self._baudrate = int(self.get_parameter('baudrate').get_parameter_value().integer_value)
        self._explicit_simulation = bool(self.get_parameter('simulate_hardware').value)
        self._allow_simulation_fallback = bool(self.get_parameter('allow_simulation_fallback').value)
        self._authoritative_simulation = bool(self.get_parameter('authoritative_simulation').value)
        self._execution_mode = str(self.get_parameter('execution_mode').value or 'protocol_bridge')
        self._simulate = self._explicit_simulation
        self._simulated_fallback = False
        self._connection_error: str | None = None
        self._heartbeat = Watchdog(timeout_seconds=float(self.get_parameter('heartbeat_timeout').value))
        self._ser = None
        self._lock = threading.Lock()
        self._sim_frames: List[ScheduledSimFrame] = []
        self._sim_report_period_sec = float(self.get_parameter('sim_report_period_sec').value)
        self._last_sim_report_at = 0.0
        self._sim_state: Dict[str, Any] = {
            'home_ok': True,
            'gripper_ok': True,
            'gripper_open': True,
            'motion_busy': False,
            'limit_triggered': False,
            'estop_pressed': False,
            'hardware_fault_code': 0,
            'joint_position': [0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
            'joint_velocity': [0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
            'last_stage': '',
            'last_kind': '',
            'last_result': 'idle',
            'transport_state': 'idle',
            'transport_result': 'idle',
            'actuation_state': 'idle',
            'actuation_result': 'idle',
            'execution_state': 'idle',
            'result_code': 'idle',
        }

        self._tx_sub = self.create_subscription(String, TopicNames.HARDWARE_STM32_TX, self._on_tx, 50)
        self._rx_pub = self.create_managed_publisher(String, TopicNames.HARDWARE_STM32_RX, 50)
        self._status_pub = self.create_managed_publisher(String, TopicNames.HARDWARE_STM32_LINK, 10)

        self.create_timer(0.05, self._poll_link)
        self._try_open()

    def _transport_mode(self) -> str:
        if self._simulate:
            return 'simulated'
        if self._ser is not None:
            return 'real'
        return 'unavailable'

    def _authoritative(self) -> bool:
        transport_mode = self._transport_mode()
        if transport_mode == 'simulated' and self._authoritative_simulation and self._explicit_simulation and not self._simulated_fallback:
            return True
        return transport_mode == 'real' and not self._simulated_fallback

    def _publish_link_status(self) -> None:
        transport_mode = self._transport_mode()
        online = (transport_mode == 'real') or (transport_mode == 'simulated' and (self._explicit_simulation or self._simulated_fallback))
        self._status_pub.publish(
            String(
                data=json.dumps(
                    {
                        'online': online,
                        'expired': self._heartbeat.expired(),
                        'port': self._port,
                        'transportMode': transport_mode,
                        'authoritative': self._authoritative(),
                        'simulate_hardware': self._simulate,
                        'explicitSimulation': self._explicit_simulation,
                        'authoritativeSimulation': self._authoritative_simulation,
                        'simulatedFallback': self._simulated_fallback,
                        'allowSimulationFallback': self._allow_simulation_fallback,
                        'executionMode': self._execution_mode,
                        'connectionError': self._connection_error,
                        'portConfigured': bool(str(self._port).strip()),
                        'portOpened': self._ser is not None,
                    },
                    ensure_ascii=False,
                )
            )
        )

    def _activate_simulated_fallback(self, reason: str) -> None:
        if not self._allow_simulation_fallback:
            self._simulate = False
            self._ser = None
            self._connection_error = reason
            self.get_logger().error(f'STM32 transport unavailable without fallback permission: {reason}')
            return
        self._simulate = True
        self._simulated_fallback = True
        self._ser = None
        self._connection_error = reason
        self.get_logger().warn(f'Entering explicit simulated fallback transport mode: {reason}')

    def _try_open(self) -> None:
        if self._explicit_simulation:
            self._simulate = True
            self._simulated_fallback = False
            self._connection_error = None
            self.get_logger().info('STM32 serial node running in explicit simulated transport mode.')
            return
        if serial is None:
            self._ser = None
            self._activate_simulated_fallback('pyserial dependency unavailable')
            return
        try:
            self._ser = serial.Serial(self._port, self._baudrate, timeout=0.02)
            self._simulate = False
            self._simulated_fallback = False
            self._connection_error = None
            self.get_logger().info(f'Connected STM32 serial: {self._port} @ {self._baudrate}')
        except Exception as exc:
            self._ser = None
            self._activate_simulated_fallback(str(exc))

    def _on_tx(self, msg: String) -> None:
        if not self.runtime_active:
            return
        if self._simulate:
            self._simulate_command(msg.data)
            return
        if self._ser is None:
            self.get_logger().warn(f'Serial unavailable, dropping TX: {msg.data}')
            self._publish_link_status()
            return
        try:
            with self._lock:
                self._ser.write(bytes.fromhex(msg.data))
        except Exception as exc:
            self._activate_simulated_fallback(f'serial write failed: {exc}')

    def _queue_simulated_state_report(self, *, now: float | None = None, last_sequence: int = -1, task_id: str = '') -> None:
        """Queue one simulated REPORT_STATE frame to keep the semantic state fresh.

        Args:
            now: Optional monotonic timestamp used to schedule the frame.
            last_sequence: Command sequence associated with the state report.
            task_id: Optional task identifier echoed back to observers.

        Returns:
            None.

        Raises:
            Does not raise. Scheduling is best-effort for simulated transport only.
        """
        timestamp = time.monotonic() if now is None else now
        report = build_frame(HardwareCommand.REPORT_STATE, max(0, int(last_sequence)) % 255, {
            **self._sim_state,
            'last_sequence': int(last_sequence),
            'task_id': str(task_id or ''),
        })
        self._sim_frames.append(ScheduledSimFrame(timestamp + 0.01, report.encode().hex()))
        self._last_sim_report_at = timestamp

    def _simulate_command(self, raw_hex: str) -> None:
        try:
            frame = decode_hex_frame(raw_hex)
            payload = decode_payload(frame.payload)
            now = time.monotonic()
            ack = build_frame(HardwareCommand.ACK, frame.sequence, {
                'ack_sequence': frame.sequence,
                'command': frame.command,
                'ok': True,
                'transport_state': 'accepted',
                'transport_result': 'accepted',
                'actuation_state': 'pending',
                'actuation_result': 'accepted',
                'execution_state': 'pending',
                'result_code': 'accepted',
            })
            self._sim_frames.append(ScheduledSimFrame(now + 0.02, ack.encode().hex()))

            kind = str(payload.get('kind', ''))
            stage = str(payload.get('stage', ''))
            self._sim_state.update({
                'motion_busy': kind in {'EXEC_STAGE', 'HOME', 'OPEN_GRIPPER', 'CLOSE_GRIPPER'},
                'last_stage': stage,
                'last_kind': kind,
                'last_result': 'accepted',
                'transport_state': 'accepted',
                'transport_result': 'accepted',
                'actuation_state': 'pending',
                'actuation_result': 'accepted',
                'execution_state': 'pending',
                'result_code': 'accepted',
            })

            delay = 0.08
            if kind == 'STOP':
                self._sim_state['motion_busy'] = False
                self._sim_state['last_result'] = 'stopped'
                self._sim_state['transport_state'] = 'completed'
                self._sim_state['transport_result'] = 'accepted'
                self._sim_state['actuation_state'] = 'canceled'
                self._sim_state['actuation_result'] = 'stopped'
                self._sim_state['execution_state'] = 'canceled'
                self._sim_state['result_code'] = 'stopped'
                delay = 0.03
            elif kind == 'HOME':
                self._sim_state['home_ok'] = True
                self._sim_state['motion_busy'] = False
                self._sim_state['last_result'] = 'home_ok'
                self._sim_state['transport_state'] = 'completed'
                self._sim_state['transport_result'] = 'accepted'
                self._sim_state['actuation_state'] = 'succeeded'
                self._sim_state['actuation_result'] = 'homed'
                self._sim_state['execution_state'] = 'succeeded'
                self._sim_state['result_code'] = 'homed'
                delay = 0.12
            elif kind == 'OPEN_GRIPPER':
                self._sim_state['gripper_ok'] = True
                self._sim_state['gripper_open'] = True
                self._sim_state['motion_busy'] = False
                self._sim_state['last_result'] = 'opened'
                self._sim_state['transport_state'] = 'completed'
                self._sim_state['transport_result'] = 'accepted'
                self._sim_state['actuation_state'] = 'succeeded'
                self._sim_state['actuation_result'] = 'gripper_open'
                self._sim_state['execution_state'] = 'succeeded'
                self._sim_state['result_code'] = 'gripper_open'
                delay = 0.06
            elif kind == 'CLOSE_GRIPPER':
                self._sim_state['gripper_ok'] = True
                self._sim_state['gripper_open'] = False
                self._sim_state['motion_busy'] = False
                self._sim_state['last_result'] = 'closed'
                self._sim_state['transport_state'] = 'completed'
                self._sim_state['transport_result'] = 'accepted'
                self._sim_state['actuation_state'] = 'succeeded'
                self._sim_state['actuation_result'] = 'gripper_closed'
                self._sim_state['execution_state'] = 'succeeded'
                self._sim_state['result_code'] = 'gripper_closed'
                delay = 0.06
            elif kind == 'EXEC_STAGE':
                self._sim_state['motion_busy'] = False
                self._sim_state['last_result'] = 'done'
                self._sim_state['transport_state'] = 'completed'
                self._sim_state['transport_result'] = 'accepted'
                self._sim_state['actuation_state'] = 'succeeded'
                self._sim_state['actuation_result'] = 'stage_completed'
                self._sim_state['execution_state'] = 'succeeded'
                self._sim_state['result_code'] = 'stage_completed'
                delay = 0.10
            elif kind == 'RESET_FAULT':
                self._sim_state['hardware_fault_code'] = 0
                self._sim_state['limit_triggered'] = False
                self._sim_state['estop_pressed'] = False
                self._sim_state['last_result'] = 'reset'
                self._sim_state['transport_state'] = 'completed'
                self._sim_state['transport_result'] = 'accepted'
                self._sim_state['actuation_state'] = 'succeeded'
                self._sim_state['actuation_result'] = 'reset'
                self._sim_state['execution_state'] = 'succeeded'
                self._sim_state['result_code'] = 'reset'
                delay = 0.05
            elif kind == 'QUERY_STATE':
                self._sim_state['last_result'] = 'state'
                self._sim_state['transport_state'] = 'completed'
                self._sim_state['transport_result'] = 'accepted'
                self._sim_state['actuation_state'] = 'succeeded'
                self._sim_state['actuation_result'] = 'state_snapshot'
                self._sim_state['execution_state'] = 'succeeded'
                self._sim_state['result_code'] = 'state_snapshot'
                delay = 0.03
            elif kind == 'JOG_JOINT':
                joint_index = max(0, min(len(self._sim_state['joint_position']) - 1, int(payload.get('jointIndex', 0))))
                direction = 1 if int(payload.get('direction', 1)) >= 0 else -1
                step_deg = float(payload.get('stepDeg', 0.0))
                step_rad = direction * (step_deg * 3.141592653589793 / 180.0)
                self._sim_state['joint_position'][joint_index] = float(self._sim_state['joint_position'][joint_index] + step_rad)
                self._sim_state['joint_velocity'][joint_index] = abs(step_rad)
                self._sim_state['motion_busy'] = False
                self._sim_state['last_result'] = 'jogged'
                self._sim_state['transport_state'] = 'completed'
                self._sim_state['transport_result'] = 'accepted'
                self._sim_state['actuation_state'] = 'succeeded'
                self._sim_state['actuation_result'] = 'joint_jogged'
                self._sim_state['execution_state'] = 'succeeded'
                self._sim_state['result_code'] = 'joint_jogged'
                delay = 0.04
            elif kind == 'SERVO_CARTESIAN':
                axis = str(payload.get('axis', 'x'))
                delta = float(payload.get('delta', 0.0))
                axis_map = {'x': 0, 'y': 1, 'z': 2, 'rx': 3, 'ry': 4, 'rz': 0}
                joint_index = axis_map.get(axis, 0)
                self._sim_state['joint_position'][joint_index] = float(self._sim_state['joint_position'][joint_index] + delta)
                self._sim_state['joint_velocity'][joint_index] = abs(delta)
                self._sim_state['motion_busy'] = False
                self._sim_state['last_result'] = f'servo_{axis}'
                self._sim_state['transport_state'] = 'completed'
                self._sim_state['transport_result'] = 'accepted'
                self._sim_state['actuation_state'] = 'succeeded'
                self._sim_state['actuation_result'] = f'servo_{axis}'
                self._sim_state['execution_state'] = 'succeeded'
                self._sim_state['result_code'] = f'servo_{axis}'
                delay = 0.04

            self._queue_simulated_state_report(now=now + delay - 0.01, last_sequence=frame.sequence, task_id=str(payload.get('task_id', '')))
            self._heartbeat.tick()
        except Exception as exc:
            self.get_logger().error(f'Failed to simulate command: {exc}')

    def _poll_link(self) -> None:
        if not self.runtime_active:
            return
        if not self._simulate and self._ser is not None:
            try:
                with self._lock:
                    raw = self._ser.readline()
                if raw:
                    self._heartbeat.tick()
                    self._rx_pub.publish(String(data=raw.hex()))
            except Exception as exc:
                self._activate_simulated_fallback(f'serial read failed: {exc}')

        if self._simulate:
            now = time.monotonic()
            if self._sim_report_period_sec > 0.0 and (now - self._last_sim_report_at) >= self._sim_report_period_sec:
                self._queue_simulated_state_report(now=now)
            ready = [frame for frame in self._sim_frames if frame.publish_at <= now]
            self._sim_frames = [frame for frame in self._sim_frames if frame.publish_at > now]
            for frame in ready:
                self._rx_pub.publish(String(data=frame.frame_hex))
                self._heartbeat.tick()

        self._publish_link_status()



def main(args=None) -> None:
    lifecycle_main(Stm32SerialNode, args=args)
