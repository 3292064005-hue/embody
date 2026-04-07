from __future__ import annotations

import asyncio
import json
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Literal

from .runtime_projection import EVENT_TOPIC_BY_EVENT, ProjectionTopic

from fastapi import WebSocket

from .models import now_iso


@dataclass
class ClientConnection:
    websocket: WebSocket
    queue: asyncio.Queue[str] = field(default_factory=lambda: asyncio.Queue(maxsize=100))
    sender_task: asyncio.Task | None = None
    bootstrapped: bool = False
    pending: deque[str] = field(default_factory=deque)
    snapshot_revision: int | None = None


DeliveryMode = Literal['snapshot', 'delta', 'event']


class WebSocketManager:
    """Track websocket clients and deliver ordered runtime envelopes.

    Boundary behavior:
        - Runtime projection topics carry per-topic revisions so clients can
          suppress stale replays or duplicate bootstrap frames.
        - Bootstrap snapshots and live delta updates are explicitly labeled with
          ``deliveryMode`` instead of relying on position in the stream.
        - Non-projection events (audit/log/heartbeat) remain plain event frames
          without synthetic topic revisions.
    """

    def __init__(self) -> None:
        self._connections: dict[int, ClientConnection] = {}
        self._lock = asyncio.Lock()
        self._seq = 0
        self._recent_events: deque[str] = deque(maxlen=50)
        self._topic_revisions: dict[ProjectionTopic, int] = {}

    async def connect(self, websocket: WebSocket) -> ClientConnection:
        await websocket.accept()
        conn = ClientConnection(websocket=websocket)
        conn.sender_task = asyncio.create_task(self._sender(conn))
        async with self._lock:
            self._connections[id(websocket)] = conn
        return conn

    async def disconnect(self, websocket: WebSocket) -> None:
        async with self._lock:
            conn = self._connections.pop(id(websocket), None)
        if conn and conn.sender_task:
            conn.sender_task.cancel()
            try:
                await conn.sender_task
            except BaseException:
                pass

    async def _sender(self, conn: ClientConnection) -> None:
        while True:
            payload = await conn.queue.get()
            await conn.websocket.send_text(payload)


    def _projection_topic(self, event: str) -> ProjectionTopic | None:
        return EVENT_TOPIC_BY_EVENT.get(event)

    def _current_topic_revision(self, topic: ProjectionTopic) -> int:
        return int(self._topic_revisions.get(topic, 0))

    def _next_topic_revision(self, topic: ProjectionTopic) -> int:
        revision = self._current_topic_revision(topic) + 1
        self._topic_revisions[topic] = revision
        return revision

    def _encode_envelope(
        self,
        event: str,
        data: Any,
        *,
        snapshot_version: int | None = None,
        bootstrap_complete: bool | None = None,
        delivery_mode: DeliveryMode = 'event',
        topic: ProjectionTopic | None = None,
        topic_revision: int | None = None,
    ) -> str:
        self._seq += 1
        envelope = {
            'event': event,
            'timestamp': now_iso(),
            'source': 'gateway',
            'seq': self._seq,
            'schemaVersion': '1.1',
            'data': data,
        }
        if snapshot_version is not None:
            envelope['snapshotVersion'] = int(snapshot_version)
        if bootstrap_complete is not None:
            envelope['bootstrapComplete'] = bool(bootstrap_complete)
        envelope['deliveryMode'] = delivery_mode
        if topic is not None:
            envelope['topic'] = topic
        if topic_revision is not None:
            envelope['topicRevision'] = int(topic_revision)
        return json.dumps(envelope, ensure_ascii=False)

    def _build_envelope(
        self,
        event: str,
        data: Any,
        *,
        record_recent: bool = True,
        snapshot_version: int | None = None,
        bootstrap_complete: bool | None = None,
        delivery_mode: DeliveryMode = 'event',
        topic: ProjectionTopic | None = None,
        topic_revision: int | None = None,
    ) -> str:
        payload = self._encode_envelope(
            event,
            data,
            snapshot_version=snapshot_version,
            bootstrap_complete=bootstrap_complete,
            delivery_mode=delivery_mode,
            topic=topic,
            topic_revision=topic_revision,
        )
        if record_recent:
            self._recent_events.append(payload)
        return payload

    async def publish(self, event: str, data: Any) -> None:
        topic = self._projection_topic(event)
        topic_revision = self._next_topic_revision(topic) if topic is not None else None
        delivery_mode: DeliveryMode = 'delta' if topic is not None else 'event'
        envelope = self._build_envelope(
            event,
            data,
            record_recent=True,
            delivery_mode=delivery_mode,
            topic=topic,
            topic_revision=topic_revision,
        )
        async with self._lock:
            connections = list(self._connections.values())
        stale: list[WebSocket] = []
        for conn in connections:
            try:
                if conn.bootstrapped:
                    conn.queue.put_nowait(envelope)
                else:
                    conn.pending.append(envelope)
            except Exception:
                stale.append(conn.websocket)
        for ws in stale:
            await self.disconnect(ws)

    async def send_initial_snapshot(self, websocket: WebSocket, events: list[tuple[str, Any]], *, snapshot_revision: int | None = None) -> None:
        """Send a private bootstrap snapshot to a connected websocket client.

        Args:
            websocket: Connected client that has already been registered with :meth:`connect`.
            events: Ordered list of runtime projection frames. Each item is a ``(event, data)`` tuple.
            snapshot_revision: Monotonic bootstrap snapshot identifier assigned by the runtime publisher.

        Returns:
            None.

        Raises:
            Does not raise. Missing/disconnected sockets are ignored so late bootstrap
            attempts cannot break the connection lifecycle.
        """
        async with self._lock:
            conn = self._connections.get(id(websocket))
        if conn is None:
            return
        revision = int(snapshot_revision or 1)
        conn.snapshot_revision = revision
        total = len(events)
        for index, (event, data) in enumerate(events, start=1):
            topic = self._projection_topic(event)
            topic_revision = self._current_topic_revision(topic) if topic is not None else None
            await conn.queue.put(
                self._build_envelope(
                    event,
                    data,
                    record_recent=False,
                    snapshot_version=revision,
                    bootstrap_complete=(index == total),
                    delivery_mode='snapshot',
                    topic=topic,
                    topic_revision=topic_revision,
                )
            )
        conn.bootstrapped = True
        while conn.pending:
            await conn.queue.put(conn.pending.popleft())

    async def replay_recent(self, websocket: WebSocket, *, limit: int = 10) -> None:
        async with self._lock:
            conn = self._connections.get(id(websocket))
        if conn is None:
            return
        normalized = max(1, min(int(limit), len(self._recent_events) or 1))
        for payload in list(self._recent_events)[-normalized:]:
            await conn.queue.put(payload)
