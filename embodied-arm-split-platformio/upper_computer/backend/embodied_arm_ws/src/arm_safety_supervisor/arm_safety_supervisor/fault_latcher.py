from __future__ import annotations


class FaultLatcher:
    def __init__(self) -> None:
        self.last_fault_code = 0

    def latch(self, fault_code: int) -> int:
        self.last_fault_code = int(fault_code)
        return self.last_fault_code

    def clear(self) -> None:
        self.last_fault_code = 0
