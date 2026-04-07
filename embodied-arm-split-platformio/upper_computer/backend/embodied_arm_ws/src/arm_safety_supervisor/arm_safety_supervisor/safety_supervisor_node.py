from __future__ import annotations

import json
import time

import rclpy
from arm_backend_common.lifecycle_support import ManagedLifecycleNode, lifecycle_main
from std_msgs.msg import String

from arm_backend_common.enums import FaultCode, SystemMode
from arm_common import MsgTypes, SrvTypes, TopicNames, ServiceNames, parse_readiness_state_message

FaultReport = MsgTypes.FaultReport
HardwareState = MsgTypes.HardwareState
ReadinessState = MsgTypes.ReadinessState
SystemState = MsgTypes.SystemState
TaskEvent = MsgTypes.TaskEvent
StopTask = SrvTypes.StopTask
from .policy import SafetyPolicy


class SafetySupervisorNode(ManagedLifecycleNode):
    def __init__(self) -> None:
        super().__init__('safety_supervisor')
        self.declare_parameter('publish_period_sec', 0.5)
        self.declare_parameter('fault_latch_sec', 1.0)
        self._policy = SafetyPolicy()
        self._hardware = {}
        self._readiness = {}
        self._system_mode = int(SystemMode.BOOT)
        self._last_signature = ''
        self._last_emit = 0.0

        self._fault_pub = self.create_managed_publisher(FaultReport, TopicNames.FAULT_REPORT, 20)
        self._stop_pub = self.create_managed_publisher(String, TopicNames.INTERNAL_STOP_CMD, 20)
        self._event_pub = self.create_managed_publisher(TaskEvent, TopicNames.LOG_EVENT, 50)
        self._health_pub = self.create_managed_publisher(String, TopicNames.DIAGNOSTICS_HEALTH, 20)

        self.create_subscription(HardwareState, TopicNames.HARDWARE_STATE, self._on_hardware, 20)
        self.create_subscription(SystemState, TopicNames.SYSTEM_STATE, self._on_system, 20)
        self.create_subscription(String, TopicNames.READINESS_STATE, self._on_readiness, 20)
        if ReadinessState is not object:
            self.create_subscription(ReadinessState, TopicNames.READINESS_STATE_TYPED, self._on_readiness_typed, 20)
        self.create_service(StopTask, ServiceNames.STOP, self._handle_stop)
        self.create_timer(float(self.get_parameter('publish_period_sec').value), self._evaluate)

    def _on_hardware(self, msg: HardwareState) -> None:
        self._hardware = {
            'stm32_online': bool(msg.stm32_online),
            'esp32_online': bool(msg.esp32_online),
            'estop_pressed': bool(msg.estop_pressed),
            'home_ok': bool(msg.home_ok),
            'gripper_ok': bool(msg.gripper_ok),
            'motion_busy': bool(msg.motion_busy),
            'limit_triggered': bool(msg.limit_triggered),
            'hardware_fault_code': int(msg.hardware_fault_code),
        }

    def _on_system(self, msg: SystemState) -> None:
        self._system_mode = int(msg.system_mode)

    def _on_readiness(self, msg: String) -> None:
        try:
            self._readiness = json.loads(msg.data) if msg.data else {}
        except Exception:
            self._readiness = {}

    def _on_readiness_typed(self, msg: ReadinessState) -> None:
        self._readiness = parse_readiness_state_message(msg)

    def _handle_stop(self, request: StopTask.Request, response: StopTask.Response) -> StopTask.Response:
        if not self.runtime_active:
            response.success = False
            response.message = 'safety supervisor inactive'
            return response
        del request
        self._publish_stop('manual_stop', FaultCode.NONE)
        response.success = True
        response.message = 'Stop signal published'
        return response

    def _evaluate(self) -> None:
        if not self.runtime_active:
            return
        decision = self._policy.evaluate(system_mode=self._system_mode, hardware=self._hardware, readiness=self._readiness)
        now = time.monotonic()
        signature = f"{int(decision.fault_code)}:{decision.event_type}:{decision.message}"
        if decision.stop_requested and (signature != self._last_signature or now - self._last_emit >= float(self.get_parameter('fault_latch_sec').value)):
            self._publish_stop(decision.message, decision.fault_code)
            self._publish_fault(decision)
            self._emit_event('WARN' if decision.severity == 'warn' else 'ERROR', 'safety_supervisor', decision.event_type, int(decision.fault_code), decision.message)
            self._last_signature = signature
            self._last_emit = now
        self._publish_health(decision)

    def _publish_stop(self, message: str, fault_code: FaultCode) -> None:
        payload = {
            'reason': 'safety_supervisor',
            'message': message,
            'faultCode': int(fault_code),
        }
        self._stop_pub.publish(String(data=json.dumps(payload, ensure_ascii=False)))

    def _publish_fault(self, decision) -> None:
        msg = FaultReport()
        msg.stamp = self.get_clock().now().to_msg()
        msg.code = int(decision.fault_code)
        msg.source = 'safety_supervisor'
        msg.severity = decision.severity
        msg.task_id = ''
        msg.message = decision.message
        self._fault_pub.publish(msg)

    def _emit_event(self, level: str, source: str, event_type: str, code: int, message: str) -> None:
        event = TaskEvent()
        event.stamp = self.get_clock().now().to_msg()
        event.level = level
        event.source = source
        event.event_type = event_type
        event.task_id = ''
        event.code = int(code)
        event.message = message
        self._event_pub.publish(event)

    def _publish_health(self, decision) -> None:
        payload = {
            'source': 'safety_supervisor',
            'mode': int(self._system_mode),
            'safe': not decision.stop_requested,
            'severity': decision.severity,
            'faultCode': int(decision.fault_code),
            'message': decision.message,
            'readinessAllReady': bool(self._readiness.get('allReady', False)) if self._readiness else None,
            'timestampMonotonic': time.monotonic(),
        }
        self._health_pub.publish(String(data=json.dumps(payload, ensure_ascii=False)))


def main(args=None) -> None:
    lifecycle_main(SafetySupervisorNode, args=args)
