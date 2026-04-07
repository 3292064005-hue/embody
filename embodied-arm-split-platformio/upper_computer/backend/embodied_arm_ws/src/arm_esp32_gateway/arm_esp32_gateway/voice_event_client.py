from arm_common import TopicNames


class VoiceEventClient:
    def to_event(self, phrase: str) -> dict:
        return {"topic": TopicNames.VOICE_EVENTS, "phrase": phrase}
