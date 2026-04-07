from __future__ import annotations

from collections import deque


class TaskQueue:
    def __init__(self, capacity: int = 32) -> None:
        self.capacity = capacity
        self._queue = deque()

    def push(self, item) -> bool:
        if len(self._queue) >= self.capacity:
            return False
        self._queue.append(item)
        return True

    def pop(self):
        return self._queue.popleft() if self._queue else None

    def __len__(self) -> int:
        return len(self._queue)
