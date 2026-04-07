from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Dict

from arm_backend_common.enums import HardwareCommand


@dataclass
class PendingCommand:
    sequence: int
    payload: Dict[str, Any]
    command: HardwareCommand
    sent_at: float
    acked: bool = False
    attempts: int = 1
    ack_timeout_sec: float = 0.35
    completion_timeout_sec: float = 1.0

    def to_summary(self, now: float) -> Dict[str, Any]:
        return {
            "sequence": self.sequence,
            "kind": self.payload.get("kind", ""),
            "stage": self.payload.get("stage", ""),
            "task_id": self.payload.get("task_id", ""),
            "acked": self.acked,
            "attempts": self.attempts,
            "age_sec": max(0.0, now - self.sent_at),
        }
