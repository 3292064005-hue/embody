from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict

from arm_backend_common.enums import HardwareCommand


@dataclass
class PendingCommand:
    """Dispatcher-side tracked command awaiting ACK/DONE feedback.

    Args:
        sequence: STM32 transport sequence allocated by the dispatcher.
        payload: Original command payload sent toward transport.
        command: Low-level hardware enum encoded into the serial frame.
        sent_at: Monotonic timestamp of the latest TX attempt.
        acked: Whether ACK feedback has already arrived.
        attempts: Number of transport attempts already sent.
        ack_timeout_sec: Timeout for ACK feedback.
        completion_timeout_sec: Timeout for terminal completion feedback.
    """

    sequence: int
    payload: Dict[str, Any]
    command: HardwareCommand
    sent_at: float
    acked: bool = False
    attempts: int = 1
    ack_timeout_sec: float = 0.35
    completion_timeout_sec: float = 1.0

    def to_summary(self, now: float) -> Dict[str, Any]:
        """Build a stable summary for diagnostics and hardware-state projection."""
        return {
            'sequence': self.sequence,
            'command_id': self.payload.get('command_id', ''),
            'plan_id': self.payload.get('plan_id', ''),
            'kind': self.payload.get('kind', ''),
            'stage': self.payload.get('stage', ''),
            'task_id': self.payload.get('task_id', ''),
            'acked': self.acked,
            'attempts': self.attempts,
            'age_sec': max(0.0, now - self.sent_at),
        }
