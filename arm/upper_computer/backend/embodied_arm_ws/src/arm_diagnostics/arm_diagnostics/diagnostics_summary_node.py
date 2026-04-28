from __future__ import annotations

import json
import time

import rclpy
from arm_backend_common.lifecycle_support import ManagedLifecycleNode, lifecycle_main
from std_msgs.msg import String

from arm_common import MsgTypes, TopicNames, build_diagnostics_summary_message, parse_task_status_message

DiagnosticsSummary = MsgTypes.DiagnosticsSummary
HardwareState = MsgTypes.HardwareState
SystemState = MsgTypes.SystemState
TaskEvent = MsgTypes.TaskEvent
TaskStatusMsg = MsgTypes.TaskStatus


class DiagnosticsSummaryNode(ManagedLifecycleNode):
    def __init__(self) -> None:
        super().__init__("diagnostics_summary")
        self._system = None
        self._hardware = None
        self._last_event = None
        self._hardware_summary = {}
        self._bringup = {}
        self._task_status = {}
        self._feedback_stats = {"ack": 0, "nack": 0, "timeout": 0, "retry": 0, "fault": 0, "done": 0, "sent": 0, "soft_done": 0}
        self._pub = self.create_managed_publisher(String, TopicNames.DIAGNOSTICS_SUMMARY, 10)
        self._typed_pub = self.create_managed_publisher(DiagnosticsSummary, TopicNames.DIAGNOSTICS_SUMMARY_TYPED, 10) if DiagnosticsSummary is not object else None
        self._health_pub = self.create_managed_publisher(String, TopicNames.DIAGNOSTICS_HEALTH, 10)
        self.create_subscription(SystemState, TopicNames.SYSTEM_STATE, self._on_system, 20)
        self.create_subscription(HardwareState, TopicNames.HARDWARE_STATE, self._on_hardware, 20)
        self.create_subscription(String, TopicNames.HARDWARE_SUMMARY, self._on_hardware_summary, 20)
        self.create_subscription(String, TopicNames.BRINGUP_STATUS, self._on_bringup, 20)
        self.create_subscription(String, TopicNames.HARDWARE_FEEDBACK, self._on_feedback, 50)
        self.create_subscription(String, TopicNames.TASK_STATUS, self._on_task_status, 50)
        if TaskStatusMsg is not object:
            self.create_subscription(TaskStatusMsg, TopicNames.TASK_STATUS_TYPED, self._on_task_status_typed, 50)
        self.create_subscription(TaskEvent, TopicNames.LOG_EVENT, self._on_event, 50)
        self.create_timer(0.5, self._publish)

    def _on_system(self, msg: SystemState) -> None:
        self._system = msg

    def _on_hardware(self, msg: HardwareState) -> None:
        self._hardware = msg

    def _on_bringup(self, msg: String) -> None:
        try:
            self._bringup = json.loads(msg.data)
        except Exception:
            self._bringup = {}

    def _on_hardware_summary(self, msg: String) -> None:
        try:
            self._hardware_summary = json.loads(msg.data)
        except Exception:
            self._hardware_summary = {}

    def _on_task_status(self, msg: String) -> None:
        try:
            self._task_status = json.loads(msg.data) if msg.data else {}
        except Exception:
            self._task_status = {}

    def _on_task_status_typed(self, msg: TaskStatusMsg) -> None:
        self._task_status = parse_task_status_message(msg)

    def _on_feedback(self, msg: String) -> None:
        try:
            payload = json.loads(msg.data)
            status = str(payload.get("status", ""))
            if status in self._feedback_stats:
                self._feedback_stats[status] += 1
        except Exception:
            pass

    def _on_event(self, msg: TaskEvent) -> None:
        self._last_event = {
            "level": msg.level,
            "source": msg.source,
            "event_type": msg.event_type,
            "task_id": msg.task_id,
            "code": msg.code,
            "message": msg.message,
        }

    def _compose_payload(self) -> dict:
        health = "ok"
        problems = []
        if self._hardware is not None:
            if not self._hardware.stm32_online:
                health = "degraded"
                problems.append("stm32_offline")
            if self._hardware.estop_pressed:
                health = "fault"
                problems.append("estop_pressed")
            if self._hardware.limit_triggered:
                health = "fault"
                problems.append("limit_triggered")
            if int(self._hardware.hardware_fault_code) != 0:
                health = "fault"
                problems.append("hardware_fault")
        if self._system is not None and int(self._system.active_fault_code) != 0:
            health = "fault"
            problems.append("system_fault")
        if self._bringup and not bool(self._bringup.get("ready", False)) and health == "ok":
            health = "warming_up"
            problems.append("bringup_incomplete")
        return {
            "stamp_monotonic": time.monotonic(),
            "health": health,
            "problems": problems,
            "bringup": self._bringup,
            "taskStatus": self._task_status,
            "system": None if self._system is None else {
                "mode": int(self._system.system_mode),
                "task_id": self._system.current_task_id,
                "stage": self._system.current_stage,
                "hardware_ready": self._system.hardware_ready,
                "motion_ready": self._system.motion_ready,
                "vision_ready": self._system.vision_ready,
                "fault": int(self._system.active_fault_code),
                "message": self._system.message,
            },
            "hardware": None if self._hardware is None else {
                "stm32_online": self._hardware.stm32_online,
                "esp32_online": self._hardware.esp32_online,
                "estop_pressed": self._hardware.estop_pressed,
                "home_ok": self._hardware.home_ok,
                "gripper_ok": self._hardware.gripper_ok,
                "motion_busy": self._hardware.motion_busy,
                "limit_triggered": self._hardware.limit_triggered,
                "fault": int(self._hardware.hardware_fault_code),
            },
            "hardware_summary": self._hardware_summary,
            "feedback_stats": self._feedback_stats,
            "last_event": self._last_event,
        }

    def _publish(self) -> None:
        if not self.runtime_active:
            return
        payload = self._compose_payload()
        self._pub.publish(String(data=json.dumps(payload, ensure_ascii=False)))
        if self._typed_pub is not None:
            self._typed_pub.publish(build_diagnostics_summary_message(payload))
        self._health_pub.publish(String(data=json.dumps({
            'source': 'diagnostics_summary',
            'safe': payload['health'] not in {'fault'},
            'health': payload['health'],
            'problems': payload['problems'],
            'timestampMonotonic': payload['stamp_monotonic'],
        }, ensure_ascii=False)))


def main(args=None) -> None:
    lifecycle_main(DiagnosticsSummaryNode, args=args)
