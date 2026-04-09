from __future__ import annotations

from dataclasses import dataclass


@dataclass
class RetryPolicy:
    max_attempts: int
    base_backoff_seconds: float = 0.2
    max_backoff_seconds: float = 1.5

    def should_retry(self, attempt: int) -> bool:
        return attempt < self.max_attempts

    def next_backoff(self, attempt: int) -> float:
        if attempt <= 0:
            return 0.0
        delay = self.base_backoff_seconds * (2 ** (attempt - 1))
        return min(delay, self.max_backoff_seconds)
