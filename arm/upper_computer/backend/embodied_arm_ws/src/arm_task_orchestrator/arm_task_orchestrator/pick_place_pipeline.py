from __future__ import annotations


class PickPlacePipeline:
    stages = ['PERCEPTION', 'PLAN', 'EXECUTE', 'VERIFY']

    def build(self, target_id: str) -> list[dict]:
        return [{'stage': stage, 'target_id': target_id} for stage in self.stages]
