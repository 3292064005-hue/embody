from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any


@dataclass
class AwaitingCommand:
    payload: dict[str, Any]
    deadline_monotonic: float


class ExecutionAdapter:
    """Small adapter for command queue dispatch and feedback matching."""

    def next_awaiting(self, command: dict[str, Any], default_timeout_sec: float) -> AwaitingCommand:
        """Return awaiting metadata for a just-dispatched hardware command."""
        timeout_sec = float(command.get('timeout_sec', default_timeout_sec))
        return AwaitingCommand(payload=dict(command), deadline_monotonic=time.monotonic() + timeout_sec)

    def is_timed_out(self, awaiting: AwaitingCommand, *, now: float | None = None) -> bool:
        now = time.monotonic() if now is None else now
        return now > awaiting.deadline_monotonic

    def feedback_matches(self, feedback: dict[str, Any], awaiting: AwaitingCommand | dict[str, Any]) -> bool:
        payload = awaiting.payload if isinstance(awaiting, AwaitingCommand) else awaiting
        if not feedback:
            return False
        if str(feedback.get('task_id', payload.get('task_id', ''))) != str(payload.get('task_id', '')):
            return False
        if str(feedback.get('stage', payload.get('stage', ''))) != str(payload.get('stage', '')):
            return False
        return str(feedback.get('status', '')) == 'done'
