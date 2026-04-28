from __future__ import annotations

from arm_common import TopicNames


class StatusNotifier:
    """Build readiness notices sourced from ESP32 gateway polling."""

    def build_notice(self, *, online: bool, detail: str, base_url: str) -> dict[str, object]:
        return {
            'check': 'esp32_gateway',
            'ok': bool(online),
            'detail': str(detail),
            'topic': TopicNames.READINESS_UPDATE,
            'baseUrl': str(base_url),
            'staleAfterSec': 2.0,
        }
