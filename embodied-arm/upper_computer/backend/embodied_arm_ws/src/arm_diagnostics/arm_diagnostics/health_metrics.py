from __future__ import annotations


class HealthMetrics:
    def summarize(self, fps: float, latency_ms: float, rtt_ms: float) -> dict:
        return {'fps': float(fps), 'latency_ms': float(latency_ms), 'rtt_ms': float(rtt_ms)}
