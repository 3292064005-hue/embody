from __future__ import annotations

import asyncio
from typing import Any, Iterable

from .runtime_projection import ProjectionTopic, RuntimeProjectionService
from .ws_manager import WebSocketManager


class RuntimeEventPublisher:
    """Thread-safe publisher for gateway runtime events."""

    def __init__(self, ws: WebSocketManager, projection: RuntimeProjectionService) -> None:
        self._ws = ws
        self._projection = projection
        self._loop: asyncio.AbstractEventLoop | None = None
        self._snapshot_revision = 0

    def set_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """Attach the FastAPI asyncio event loop used for thread-safe publication."""
        self._loop = loop

    async def publish_topics(self, *topics: ProjectionTopic, extra_events: Iterable[tuple[str, Any]] | None = None) -> None:
        """Publish ordered runtime projection topics and optional custom events."""
        projection_events = self._projection.build_events(*topics)
        for item in projection_events:
            await self._ws.publish(item.event, item.data)
        if extra_events:
            for event_name, payload in extra_events:
                await self._ws.publish(event_name, payload)

    async def publish_custom(self, event: str, data: Any) -> None:
        """Publish a single non-projection event."""
        await self._ws.publish(event, data)

    def publish_topics_threadsafe(self, *topics: ProjectionTopic, extra_events: Iterable[tuple[str, Any]] | None = None) -> None:
        """Publish runtime topics from any thread."""
        if self._loop is None:
            raise RuntimeError('runtime publisher loop not initialized')
        asyncio.run_coroutine_threadsafe(self.publish_topics(*topics, extra_events=extra_events), self._loop)

    def publish_custom_threadsafe(self, event: str, data: Any) -> None:
        """Publish a custom event from any thread."""
        if self._loop is None:
            raise RuntimeError('runtime publisher loop not initialized')
        asyncio.run_coroutine_threadsafe(self.publish_custom(event, data), self._loop)

    async def send_initial_snapshot(self, websocket) -> None:
        """Send the canonical initial runtime snapshot to a new websocket client.

        Args:
            websocket: Connected websocket client.

        Returns:
            None.

        Raises:
            Does not raise. The method falls back to the legacy two-argument
            websocket-manager signature used by projection unit tests.
        """
        events = [(item.event, item.data) for item in self._projection.initial_snapshot_events()]
        self._snapshot_revision += 1
        try:
            await self._ws.send_initial_snapshot(websocket, events, snapshot_revision=self._snapshot_revision)
        except TypeError:
            await self._ws.send_initial_snapshot(websocket, events)
