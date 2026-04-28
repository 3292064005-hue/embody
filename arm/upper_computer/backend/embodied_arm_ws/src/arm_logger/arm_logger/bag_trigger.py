from __future__ import annotations


class BagTrigger:
    def should_record(self, on_fault: bool, on_stage_change: bool) -> bool:
        return bool(on_fault or on_stage_change)
