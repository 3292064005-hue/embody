from __future__ import annotations

import asyncio

from gateway.runtime_projection import RuntimeProjectionService
from gateway.runtime_publisher import RuntimeEventPublisher
from gateway.state import GatewayState


class _FakeWs:
    def __init__(self) -> None:
        self.events: list[tuple[str, object]] = []

    async def publish(self, event: str, data):
        self.events.append((event, data))

    async def send_initial_snapshot(self, websocket, events):
        self.events.extend(events)


def test_runtime_projection_builds_ordered_deduplicated_events():
    state = GatewayState()
    projection = RuntimeProjectionService(state)
    events = projection.build_events('readiness', 'system', 'system', 'diagnostics')
    assert [item.event for item in events] == [
        'system.state.updated',
        'readiness.state.updated',
        'diagnostics.summary.updated',
    ]


def test_runtime_event_publisher_emits_projection_once_per_topic():
    state = GatewayState()
    ws = _FakeWs()
    publisher = RuntimeEventPublisher(ws, RuntimeProjectionService(state))
    asyncio.run(publisher.publish_topics('system', 'system', 'readiness'))
    assert [event for event, _ in ws.events] == ['system.state.updated', 'readiness.state.updated']



class _CaptureWebSocket:
    def __init__(self) -> None:
        self.accepted = False
        self.frames: list[dict[str, object]] = []

    async def accept(self) -> None:
        self.accepted = True

    async def send_text(self, payload: str) -> None:
        import json

        self.frames.append(json.loads(payload))


def test_websocket_manager_marks_projection_delta_frames_with_topic_revisions():
    from gateway.ws_manager import WebSocketManager

    async def _scenario() -> list[dict[str, object]]:
        manager = WebSocketManager()
        socket = _CaptureWebSocket()
        await manager.connect(socket)
        await manager.send_initial_snapshot(socket, [], snapshot_revision=1)
        await manager.publish('system.state.updated', {'mode': 'idle'})
        await manager.publish('system.state.updated', {'mode': 'manual'})
        await asyncio.sleep(0.01)
        await manager.disconnect(socket)
        return socket.frames

    frames = asyncio.run(_scenario())
    assert [frame['deliveryMode'] for frame in frames] == ['delta', 'delta']
    assert [frame['topic'] for frame in frames] == ['system', 'system']
    assert [frame['topicRevision'] for frame in frames] == [1, 2]


def test_websocket_manager_bootstrap_snapshot_carries_current_topic_revision():
    from gateway.ws_manager import WebSocketManager

    async def _scenario() -> list[dict[str, object]]:
        manager = WebSocketManager()
        live_socket = _CaptureWebSocket()
        await manager.connect(live_socket)
        await manager.publish('system.state.updated', {'mode': 'manual'})
        await asyncio.sleep(0.01)
        bootstrap_socket = _CaptureWebSocket()
        await manager.connect(bootstrap_socket)
        await manager.send_initial_snapshot(
            bootstrap_socket,
            [
                ('system.state.updated', {'mode': 'manual'}),
                ('readiness.state.updated', {'healthy': True}),
            ],
            snapshot_revision=3,
        )
        await asyncio.sleep(0.01)
        await manager.disconnect(live_socket)
        await manager.disconnect(bootstrap_socket)
        return bootstrap_socket.frames

    frames = asyncio.run(_scenario())
    assert frames[0]['deliveryMode'] == 'snapshot'
    assert frames[0]['snapshotVersion'] == 3
    assert frames[0]['topic'] == 'system'
    assert frames[0]['topicRevision'] == 1
    assert frames[0]['bootstrapComplete'] is False
    assert frames[1]['deliveryMode'] == 'snapshot'
    assert frames[1]['topic'] == 'readiness'
    assert frames[1]['topicRevision'] == 0
    assert frames[1]['bootstrapComplete'] is True
