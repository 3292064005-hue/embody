from __future__ import annotations

from arm_common import TopicNames


class CommandRouter:
    def route(self, payload: dict) -> dict:
        return {'topic': TopicNames.INTERNAL_HARDWARE_CMD, 'payload': dict(payload)}
