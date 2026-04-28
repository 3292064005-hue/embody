from __future__ import annotations

from typing import Any, Iterable

from arm_common import TopicNames


class VoiceEventClient:
    """Normalize ESP32 voice event HTTP payloads for ROS publication."""

    @staticmethod
    def _safe_stamp_ms(value: Any) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return 0

    def to_event(self, phrase: str, *, command: str = '', event_id: str = '', stamp_ms: int = 0) -> dict[str, Any]:
        normalized_phrase = str(phrase or '').strip()
        normalized_command = str(command or normalized_phrase).strip().lower().replace(' ', '_')
        return {
            'topic': TopicNames.VOICE_EVENTS,
            'eventId': event_id or normalized_command or 'voice_event',
            'phrase': normalized_phrase,
            'command': normalized_command,
            'stampMs': self._safe_stamp_ms(stamp_ms),
        }

    def parse_events(self, payload: dict[str, Any] | list[Any] | None) -> list[dict[str, Any]]:
        source: Iterable[Any]
        if isinstance(payload, dict):
            source = payload.get('events') if isinstance(payload.get('events'), list) else [payload]
        elif isinstance(payload, list):
            source = payload
        else:
            source = []
        events: list[dict[str, Any]] = []
        for item in source:
            if isinstance(item, str):
                normalized = item.strip()
                if normalized:
                    events.append(self.to_event(normalized))
                continue
            if not isinstance(item, dict):
                continue
            phrase = str(item.get('phrase') or item.get('text') or '').strip()
            command = str(item.get('command') or item.get('intent') or phrase).strip()
            if not phrase and not command:
                continue
            event_id = str(item.get('id') or item.get('eventId') or command or phrase).strip()
            stamp_ms = self._safe_stamp_ms(item.get('stamp_ms', item.get('stampMs', 0)))
            events.append(self.to_event(phrase, command=command, event_id=event_id, stamp_ms=stamp_ms))
        return events
