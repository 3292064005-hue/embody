from __future__ import annotations


class CommLossGuard:
    def lost(self, updated_monotonic: float, now: float, timeout_sec: float) -> bool:
        return (now - updated_monotonic) > timeout_sec
