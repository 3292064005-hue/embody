from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Deque, Optional

from arm_backend_common.data_models import TaskRequest


@dataclass
class MissionQueue:
    max_size: int = 8

    def __post_init__(self) -> None:
        self._queue: Deque[TaskRequest] = deque()

    def push(self, request: TaskRequest, high_priority: bool = False) -> bool:
        if len(self._queue) >= self.max_size:
            return False
        if high_priority:
            self._queue.appendleft(request)
        else:
            self._queue.append(request)
        return True

    def pop(self) -> Optional[TaskRequest]:
        if not self._queue:
            return None
        return self._queue.popleft()

    def clear(self) -> None:
        self._queue.clear()

    def is_empty(self) -> bool:
        return not self._queue

    def size(self) -> int:
        return len(self._queue)

    def peek(self) -> Optional[TaskRequest]:
        return self._queue[0] if self._queue else None
