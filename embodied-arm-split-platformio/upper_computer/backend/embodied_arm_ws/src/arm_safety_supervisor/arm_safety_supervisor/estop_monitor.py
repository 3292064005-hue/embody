from __future__ import annotations


class EStopMonitor:
    def triggered(self, hardware: dict) -> bool:
        return bool(hardware.get('estop_pressed', False))
