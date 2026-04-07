from __future__ import annotations

import json
from pathlib import Path

import rclpy
from arm_backend_common.lifecycle_support import ManagedLifecycleNode, lifecycle_main

from arm_common import MsgTypes, TopicNames

TaskEvent = MsgTypes.TaskEvent


class EventLoggerNode(ManagedLifecycleNode):
    def __init__(self) -> None:
        super().__init__("event_logger_node")
        self.declare_parameter("log_dir", "logs")
        self._log_dir = Path(self.get_parameter("log_dir").value)
        self._event_dir = self._log_dir / "event"
        self._fault_dir = self._log_dir / "fault"
        self._event_dir.mkdir(parents=True, exist_ok=True)
        self._fault_dir.mkdir(parents=True, exist_ok=True)
        self._event_file = self._event_dir / "task_events.jsonl"
        self._fault_file = self._fault_dir / "fault_events.jsonl"
        self.create_subscription(TaskEvent, TopicNames.LOG_EVENT, self._on_event, 100)
        self.get_logger().info(f"Event logger writing to {self._event_file}")

    def _on_event(self, msg: TaskEvent) -> None:
        if not self.runtime_active:
            return
        record = {
            "stamp": {"sec": msg.stamp.sec, "nanosec": msg.stamp.nanosec},
            "level": msg.level,
            "source": msg.source,
            "event_type": msg.event_type,
            "task_id": msg.task_id,
            "code": msg.code,
            "message": msg.message,
        }
        with self._event_file.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
        if str(msg.level).upper() in {"ERROR", "FATAL"}:
            with self._fault_file.open("a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")


def main(args=None) -> None:
    lifecycle_main(EventLoggerNode, args=args)
