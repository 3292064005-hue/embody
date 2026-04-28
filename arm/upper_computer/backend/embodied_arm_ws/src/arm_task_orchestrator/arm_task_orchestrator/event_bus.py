from __future__ import annotations


class EventBus:
    def __init__(self) -> None:
        self.events = []

    def publish(self, event_type: str, payload: dict) -> dict:
        item = {'event_type': event_type, 'payload': dict(payload)}
        self.events.append(item)
        return item
