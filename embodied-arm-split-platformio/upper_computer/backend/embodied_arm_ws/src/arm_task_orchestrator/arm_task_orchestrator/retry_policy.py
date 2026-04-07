from __future__ import annotations


class RetryPolicy:
    def __init__(self, max_retry_per_target: int = 1, max_retry_per_task: int = 3) -> None:
        self.max_retry_per_target = max_retry_per_target
        self.max_retry_per_task = max_retry_per_task

    def allow(self, target_retry_count: int, task_retry_count: int) -> bool:
        return target_retry_count < self.max_retry_per_target and task_retry_count < self.max_retry_per_task
