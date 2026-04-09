from __future__ import annotations


class StateAggregator:
    def merge(self, *parts: dict) -> dict:
        merged = {}
        for part in parts:
            merged.update(part)
        return merged
