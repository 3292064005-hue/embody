from __future__ import annotations

import csv
import json
from pathlib import Path

import rclpy
from arm_backend_common.lifecycle_support import ManagedLifecycleNode, lifecycle_main
from std_msgs.msg import String

from arm_common import MsgTypes, TopicNames

SystemState = MsgTypes.SystemState
TaskEvent = MsgTypes.TaskEvent


class MetricsLoggerNode(ManagedLifecycleNode):
    def __init__(self) -> None:
        super().__init__("metrics_logger_node")
        self.declare_parameter("log_dir", "logs")
        base_dir = Path(self.get_parameter("log_dir").value)
        self._metrics_dir = base_dir / "metrics"
        self._metrics_dir.mkdir(parents=True, exist_ok=True)
        self._metrics_csv = self._metrics_dir / "task_metrics.csv"
        self._state_jsonl = self._metrics_dir / "system_state.jsonl"
        self._diag_jsonl = self._metrics_dir / "diagnostics.jsonl"
        if not self._metrics_csv.exists():
            with self._metrics_csv.open("w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(["event_type", "task_id", "code", "message"])
        self.create_subscription(TaskEvent, TopicNames.LOG_EVENT, self._on_event, 100)
        self.create_subscription(SystemState, TopicNames.SYSTEM_STATE, self._on_state, 50)
        self.create_subscription(String, TopicNames.DIAGNOSTICS_SUMMARY, self._on_diag, 20)
        self.get_logger().info(f"Metrics logger writing to {self._metrics_dir}")

    def _on_event(self, msg: TaskEvent) -> None:
        if not self.runtime_active:
            return
        if msg.event_type not in {"TASK_DONE", "TASK_RETRY", "FAULT", "TASK_START", "TASK_ENQUEUED"}:
            return
        with self._metrics_csv.open("a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([msg.event_type, msg.task_id, msg.code, msg.message])

    def _on_state(self, msg: SystemState) -> None:
        if not self.runtime_active:
            return
        record = {
            "stamp": {"sec": msg.header.stamp.sec, "nanosec": msg.header.stamp.nanosec},
            "system_mode": msg.system_mode,
            "current_task_id": msg.current_task_id,
            "current_stage": msg.current_stage,
            "hardware_ready": msg.hardware_ready,
            "motion_ready": msg.motion_ready,
            "calibration_ready": msg.calibration_ready,
            "vision_ready": msg.vision_ready,
            "emergency_stop": msg.emergency_stop,
            "active_fault_code": msg.active_fault_code,
            "message": msg.message,
        }
        with self._state_jsonl.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    def _on_diag(self, msg: String) -> None:
        if not self.runtime_active:
            return
        with self._diag_jsonl.open("a", encoding="utf-8") as f:
            f.write(msg.data + "\n")


def main(args=None) -> None:
    lifecycle_main(MetricsLoggerNode, args=args)
