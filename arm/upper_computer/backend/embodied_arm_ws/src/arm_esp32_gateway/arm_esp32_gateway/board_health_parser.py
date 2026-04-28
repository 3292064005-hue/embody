from __future__ import annotations

from typing import Any

from arm_common import TopicNames


class BoardHealthParser:
    """Normalize ESP32 HTTP payloads into one diagnostic/link contract."""

    @staticmethod
    def _safe_int(value: Any, default: int) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    def parse(self, payload: dict[str, Any] | None) -> dict[str, Any]:
        raw = dict(payload or {})
        wifi = raw.get('wifi') if isinstance(raw.get('wifi'), dict) else {}
        stream = raw.get('stream') if isinstance(raw.get('stream'), dict) else {}
        voice = raw.get('voice') if isinstance(raw.get('voice'), dict) else {}
        status = str(raw.get('status', raw.get('state', 'ok')) or 'ok').lower()
        explicit_online = raw.get('online')
        if explicit_online is None:
            online = status in {'ok', 'online', 'ready'}
        else:
            online = bool(explicit_online) and status not in {'error', 'fault', 'offline'}
        hostname = str(raw.get('hostname') or raw.get('host') or 'esp32.local')
        stream_semantic = str(stream.get('semantic') or raw.get('stream_semantic') or raw.get('streamSemantic') or 'reserved')
        frame_ingress_live = bool(stream.get('frame_ingress_live', raw.get('frame_ingress_live', raw.get('frameIngressLive', False))))
        return {
            'topic': TopicNames.DIAGNOSTICS_HEALTH,
            'online': online,
            'status': status,
            'transportMode': str(raw.get('transportMode', 'wifi')),
            'authoritative': False,
            'mode': str(raw.get('mode', 'wifi')),
            'cameraSerial': str(raw.get('camera_serial', raw.get('cameraSerial', 'esp32-camera'))),
            'streamEndpoint': str(stream.get('endpoint') or raw.get('stream_endpoint') or raw.get('streamEndpoint') or f'http://{hostname}/stream'),
            'streamSemantic': stream_semantic,
            'streamReserved': bool(raw.get('stream_reserved', raw.get('streamReserved', stream_semantic == 'reserved'))),
            'frameIngressLive': frame_ingress_live,
            'heartbeatCounter': self._safe_int(raw.get('heartbeat_counter', raw.get('heartbeatCounter', 0)) or 0, 0),
            'wifiConnected': bool(wifi.get('connected', raw.get('wifi_connected', raw.get('wifiConnected', False)))),
            'wifiRssi': self._safe_int(wifi.get('rssi', raw.get('wifi_rssi', raw.get('wifiRssi', -127))) or -127, -127),
            'hostname': hostname,
            'ipAddress': str(raw.get('ip', raw.get('ipAddress', ''))),
            'voiceTopic': str(voice.get('topic', TopicNames.VOICE_EVENTS)),
            'notifierState': str(raw.get('notifier_state', raw.get('notifierState', 'observing'))),
            'raw': raw,
        }
