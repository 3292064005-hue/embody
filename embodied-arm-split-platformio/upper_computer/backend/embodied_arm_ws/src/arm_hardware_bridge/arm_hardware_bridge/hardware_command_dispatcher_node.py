from __future__ import annotations

import json
import time
from typing import Any, Dict

import rclpy
from arm_backend_common.lifecycle_support import ManagedLifecycleNode, lifecycle_main
from std_msgs.msg import String

from arm_backend_common.enums import HardwareCommand
from arm_backend_common.protocol import build_frame, decode_hex_frame, decode_payload
from arm_common import TopicNames
from .feedback_tracker import PendingCommand

CMD_MAP = {
    "HOME": HardwareCommand.HOME,
    "STOP": HardwareCommand.STOP,
    "SAFE_HALT": HardwareCommand.STOP,
    "ESTOP": HardwareCommand.STOP,
    "EXEC_STAGE": HardwareCommand.EXEC_STAGE,
    "RESET_FAULT": HardwareCommand.RESET_FAULT,
    "OPEN_GRIPPER": HardwareCommand.OPEN_GRIPPER,
    "CLOSE_GRIPPER": HardwareCommand.CLOSE_GRIPPER,
    "QUERY_STATE": HardwareCommand.QUERY_STATE,
    "JOG_JOINT": HardwareCommand.SET_JOINTS,
    "SERVO_CARTESIAN": HardwareCommand.SET_JOINTS,
}

SOFT_COMMANDS = {"SET_MODE"}


class HardwareCommandDispatcherNode(ManagedLifecycleNode):
    def __init__(self) -> None:
        super().__init__("hardware_command_dispatcher")
        self.declare_parameter("default_completion_timeout_sec", 1.0)
        self.declare_parameter("default_ack_timeout_sec", 0.35)
        self.declare_parameter("max_retries", 2)
        self._sequence = 0
        self._pending: dict[int, PendingCommand] = {}
        self._tx_pub = self.create_managed_publisher(String, TopicNames.HARDWARE_STM32_TX, 20)
        self._feedback_pub = self.create_managed_publisher(String, TopicNames.HARDWARE_FEEDBACK, 20)
        self._summary_pub = self.create_managed_publisher(String, TopicNames.HARDWARE_DISPATCHER_STATE, 10)
        self.create_subscription(String, TopicNames.HARDWARE_COMMAND, self._on_command, 20)
        self.create_subscription(String, TopicNames.INTERNAL_HARDWARE_CMD, self._on_command, 20)
        self.create_subscription(String, TopicNames.HARDWARE_STM32_RX, self._on_rx, 50)
        self.create_timer(0.05, self._check_pending)
        self.create_timer(0.2, self._publish_summary)
        self._stats = {"sent": 0, "ack": 0, "nack": 0, "retry": 0, "timeout": 0, "done": 0, "fault": 0, "parser_error": 0, "soft_done": 0}
        self.get_logger().info("Hardware command dispatcher is ready.")

    def _on_command(self, msg: String) -> None:
        if not self.runtime_active:
            return
        try:
            payload = json.loads(msg.data)
            kind = str(payload.get("kind", ""))
            if kind in SOFT_COMMANDS:
                self._stats["soft_done"] += 1
                self._publish_feedback({
                    "status": "done",
                    "sequence": -1,
                    "kind": kind,
                    "task_id": payload.get("task_id", ""),
                    "stage": payload.get("stage", ""),
                    "result": "soft_command_applied",
                })
                return
            command = CMD_MAP.get(kind)
            if command is None:
                self.get_logger().warn(f"Unknown hardware command kind: {kind}")
                self._publish_feedback({
                    "status": "nack",
                    "sequence": -1,
                    "kind": kind,
                    "task_id": payload.get("task_id", ""),
                    "stage": payload.get("stage", ""),
                    "message": "unsupported command kind",
                })
                return
            sequence = self._allocate_sequence()
            frame = build_frame(command, sequence, payload)
            self._pending[sequence] = PendingCommand(
                sequence=sequence,
                payload=payload,
                command=command,
                sent_at=time.monotonic(),
                ack_timeout_sec=float(payload.get("ack_timeout_sec", self.get_parameter("default_ack_timeout_sec").value)),
                completion_timeout_sec=float(payload.get("timeout_sec", self.get_parameter("default_completion_timeout_sec").value)),
            )
            self._tx_pub.publish(String(data=frame.encode().hex()))
            self._stats["sent"] += 1
            self._publish_feedback({
                "status": "sent",
                "sequence": sequence,
                "kind": kind,
                "task_id": payload.get("task_id", ""),
                "stage": payload.get("stage", ""),
            })
        except Exception as exc:
            self.get_logger().error(f"Failed to dispatch hardware command: {exc}")

    def _allocate_sequence(self) -> int:
        sequence = self._sequence
        self._sequence = (self._sequence + 1) % 255
        return sequence

    def _on_rx(self, msg: String) -> None:
        try:
            frame = decode_hex_frame(msg.data)
            payload = decode_payload(frame.payload)
        except Exception as exc:
            self._stats["parser_error"] += 1
            self.get_logger().warn(f"Failed to decode STM32 RX frame: {exc}")
            return

        command = HardwareCommand(frame.command)
        if command == HardwareCommand.ACK:
            ack_sequence = int(payload.get("ack_sequence", frame.sequence))
            pending = self._pending.get(ack_sequence)
            if pending:
                pending.acked = True
                pending.sent_at = time.monotonic()
                self._stats["ack"] += 1
                self._publish_feedback({
                    "status": "ack",
                    "sequence": ack_sequence,
                    "kind": pending.payload.get("kind", ""),
                    "task_id": pending.payload.get("task_id", ""),
                    "stage": pending.payload.get("stage", ""),
                })
        elif command == HardwareCommand.NACK:
            nack_sequence = int(payload.get("ack_sequence", frame.sequence))
            pending = self._pending.pop(nack_sequence, None)
            if pending:
                self._stats["nack"] += 1
                self._publish_feedback({
                    "status": "nack",
                    "sequence": nack_sequence,
                    "kind": pending.payload.get("kind", ""),
                    "task_id": pending.payload.get("task_id", ""),
                    "stage": pending.payload.get("stage", ""),
                    "message": payload.get("message", "NACK"),
                })
        elif command == HardwareCommand.REPORT_STATE:
            last_sequence = int(payload.get("last_sequence", -1))
            pending = self._pending.pop(last_sequence, None)
            if pending:
                self._stats["done"] += 1
                self._publish_feedback({
                    "status": "done",
                    "sequence": last_sequence,
                    "kind": pending.payload.get("kind", ""),
                    "task_id": pending.payload.get("task_id", payload.get("task_id", "")),
                    "stage": pending.payload.get("stage", payload.get("last_stage", "")),
                    "result": payload.get("last_result", "done"),
                })
        elif command == HardwareCommand.REPORT_FAULT:
            self._stats["fault"] += 1
            self._publish_feedback({
                "status": "fault",
                "sequence": frame.sequence,
                "hardware_fault_code": int(payload.get("hardware_fault_code", 0)),
                "message": payload.get("message", "hardware fault"),
            })

    def _check_pending(self) -> None:
        if not self.runtime_active:
            return
        if not self._pending:
            return
        max_retries = int(self.get_parameter("max_retries").value)
        now = time.monotonic()
        for sequence, pending in list(self._pending.items()):
            elapsed = now - pending.sent_at
            if not pending.acked:
                if elapsed < pending.ack_timeout_sec:
                    continue
                if pending.attempts <= max_retries:
                    self._resend(sequence, pending, now)
                    continue
                self._pending.pop(sequence, None)
                self._stats["timeout"] += 1
                self._publish_feedback(self._timeout_payload(sequence, pending, "ack timeout"))
                continue
            if elapsed < pending.completion_timeout_sec:
                continue
            self._pending.pop(sequence, None)
            self._stats["timeout"] += 1
            self._publish_feedback(self._timeout_payload(sequence, pending, "completion timeout"))

    def _resend(self, sequence: int, pending: PendingCommand, now: float) -> None:
        frame = build_frame(pending.command, sequence, pending.payload)
        self._tx_pub.publish(String(data=frame.encode().hex()))
        pending.attempts += 1
        pending.sent_at = now
        pending.acked = False
        self._stats["retry"] += 1
        self._publish_feedback({
            "status": "retry",
            "sequence": sequence,
            "kind": pending.payload.get("kind", ""),
            "task_id": pending.payload.get("task_id", ""),
            "stage": pending.payload.get("stage", ""),
            "attempts": pending.attempts,
        })

    def _timeout_payload(self, sequence: int, pending: PendingCommand, reason: str) -> Dict[str, Any]:
        return {
            "status": "timeout",
            "sequence": sequence,
            "kind": pending.payload.get("kind", ""),
            "task_id": pending.payload.get("task_id", ""),
            "stage": pending.payload.get("stage", ""),
            "message": reason,
        }

    def _publish_feedback(self, payload: Dict[str, Any]) -> None:
        self._feedback_pub.publish(String(data=json.dumps(payload, ensure_ascii=False)))

    def _publish_summary(self) -> None:
        if not self.runtime_active:
            return
        now = time.monotonic()
        payload = {
            "pending": len(self._pending),
            "pending_details": [pending.to_summary(now) for pending in self._pending.values()],
            **self._stats,
        }
        self._summary_pub.publish(String(data=json.dumps(payload, ensure_ascii=False)))


def main(args=None) -> None:
    lifecycle_main(HardwareCommandDispatcherNode, args=args)
