from __future__ import annotations


class FPSMonitor:
    def compute(self, frame_count: int, duration_sec: float) -> float:
        return 0.0 if duration_sec <= 0 else float(frame_count) / float(duration_sec)
