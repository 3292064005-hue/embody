from __future__ import annotations


class TimeoutGuard:
    def expired(self, started_at: float, now: float, timeout_sec: float) -> bool:
        return (now - started_at) > timeout_sec
