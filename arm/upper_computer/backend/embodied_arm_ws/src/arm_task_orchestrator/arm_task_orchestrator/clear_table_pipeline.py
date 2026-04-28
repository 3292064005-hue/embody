from __future__ import annotations


class ClearTablePipeline:
    def build(self, target_ids) -> list[dict]:
        return [{'stage': 'PICK_PLACE', 'target_id': tid} for tid in list(target_ids)]
