from __future__ import annotations


class SerialRTTMonitor:
    def compute(self, sent_at: float, ack_at: float) -> float:
        return float((ack_at - sent_at) * 1000.0)
