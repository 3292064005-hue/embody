from arm_common import TopicNames


class BoardHealthParser:
    def parse(self, payload: dict) -> dict:
        return {"topic": TopicNames.DIAGNOSTICS_HEALTH, **payload}
