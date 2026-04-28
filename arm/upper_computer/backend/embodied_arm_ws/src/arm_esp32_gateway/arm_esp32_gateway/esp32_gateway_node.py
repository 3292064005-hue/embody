from __future__ import annotations

import json
from typing import Any
from urllib.error import URLError
from urllib.request import urlopen

try:
    from std_msgs.msg import String
    from arm_backend_common.lifecycle_support import ManagedLifecycleNode, lifecycle_main
    from arm_common import TopicNames
except Exception:  # pragma: no cover
    String = object
    _ARM_ROOT = '/' + 'arm'
    TopicNames = type('TopicNames', (), {
        'HARDWARE_ESP32_LINK': _ARM_ROOT + '/hardware/esp32_link',
        'DIAGNOSTICS_HEALTH': _ARM_ROOT + '/diagnostics/health',
        'READINESS_UPDATE': _ARM_ROOT + '/readiness/update',
        'VOICE_EVENTS': _ARM_ROOT + '/voice/events',
    })

    class ManagedLifecycleNode:
        def __init__(self, *args, **kwargs):
            self.runtime_active = True
        def declare_parameter(self, *args, **kwargs):
            return None
        def get_parameter(self, name):
            return type('P', (), {'value': '', 'get_parameter_value': lambda self: type('PV', (), {'string_value': ''})()})()
        def create_managed_publisher(self, *args, **kwargs):
            return type('Pub', (), {'publish': lambda self, msg: None})()
        def create_timer(self, *args, **kwargs):
            return None
        def get_logger(self):
            return type('L', (), {'warn': print})()

    def lifecycle_main(factory, args=None):
        del factory, args
        raise RuntimeError('rclpy unavailable')

from .board_health_parser import BoardHealthParser
from .status_notifier import StatusNotifier
from .voice_event_client import VoiceEventClient


class Esp32GatewayNode(ManagedLifecycleNode):
    """Poll ESP32 HTTP endpoints and republish normalized ROS contracts."""

    node_name = 'esp32_gateway'

    def __init__(self) -> None:
        super().__init__(self.node_name)
        self.declare_parameter('base_url', 'http://esp32.local')
        self.declare_parameter('health_path', '/healthz')
        self.declare_parameter('status_path', '/status')
        self.declare_parameter('voice_events_path', '/voice/events')
        self.declare_parameter('poll_period_sec', 0.5)
        self.declare_parameter('timeout_sec', 0.8)
        self.declare_parameter('publish_voice_events', True)
        self._base_url = str(self.get_parameter('base_url').value).rstrip('/')
        self._timeout_sec = float(self.get_parameter('timeout_sec').value)
        self._publish_voice_events = bool(self.get_parameter('publish_voice_events').value)
        self._health_path = str(self.get_parameter('health_path').value)
        self._status_path = str(self.get_parameter('status_path').value)
        self._voice_events_path = str(self.get_parameter('voice_events_path').value)
        self._health_parser = BoardHealthParser()
        self._voice_client = VoiceEventClient()
        self._notifier = StatusNotifier()
        self._last_voice_stamp_ms = -1
        self._link_pub = self.create_managed_publisher(String, TopicNames.HARDWARE_ESP32_LINK, 10)
        self._health_pub = self.create_managed_publisher(String, TopicNames.DIAGNOSTICS_HEALTH, 10)
        self._readiness_pub = self.create_managed_publisher(String, TopicNames.READINESS_UPDATE, 10)
        self._voice_pub = self.create_managed_publisher(String, TopicNames.VOICE_EVENTS, 10)
        self.create_timer(float(self.get_parameter('poll_period_sec').value), self._poll_once)

    def _fetch_json(self, path: str) -> dict[str, Any]:
        url = f'{self._base_url}{path}'
        try:
            with urlopen(url, timeout=self._timeout_sec) as response:
                payload = json.loads(response.read().decode('utf-8'))
        except URLError as exc:
            raise RuntimeError(f'ESP32 endpoint unreachable: {url} ({exc})') from exc
        except Exception as exc:
            raise RuntimeError(f'ESP32 endpoint returned invalid JSON: {url} ({exc})') from exc
        return payload if isinstance(payload, dict) else {'value': payload}

    def _publish_json(self, publisher, payload: dict[str, Any]) -> None:
        publisher.publish(String(data=json.dumps(payload, ensure_ascii=False)))

    def _poll_once(self) -> None:
        if not getattr(self, 'runtime_active', True):
            return
        try:
            merged = {}
            merged.update(self._fetch_json(self._health_path))
            merged.update(self._fetch_json(self._status_path))
            normalized = self._health_parser.parse(merged)
            self._publish_json(self._link_pub, normalized)
            self._publish_json(self._health_pub, normalized)
            self._publish_json(self._readiness_pub, self._notifier.build_notice(online=bool(normalized.get('online')), detail=str(normalized.get('status', 'unknown')), base_url=self._base_url))
            if self._publish_voice_events:
                self._poll_voice_events()
        except Exception as exc:
            self._publish_json(self._link_pub, {'online': False, 'transportMode': 'wifi', 'authoritative': False, 'connectionError': str(exc)})
            self._publish_json(self._health_pub, {'online': False, 'status': 'error', 'message': str(exc)})
            self._publish_json(self._readiness_pub, self._notifier.build_notice(online=False, detail='esp32_unreachable', base_url=self._base_url))
            logger = getattr(self, 'get_logger', lambda: None)()
            if logger is not None and hasattr(logger, 'warn'):
                logger.warn(str(exc))

    def _poll_voice_events(self) -> None:
        payload = self._fetch_json(self._voice_events_path)
        for event in self._voice_client.parse_events(payload):
            stamp_ms = int(event.get('stampMs', 0) or 0)
            if stamp_ms and stamp_ms <= self._last_voice_stamp_ms:
                continue
            if stamp_ms:
                self._last_voice_stamp_ms = stamp_ms
            self._publish_json(self._voice_pub, event)


def main(args=None) -> None:
    lifecycle_main(Esp32GatewayNode, args=args)
