from __future__ import annotations


class LatencyMonitor:
    def measure(self, started: float, ended: float) -> float:
        return float((ended - started) * 1000.0)
