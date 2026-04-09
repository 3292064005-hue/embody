from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from .state import GatewayState

ProjectionTopic = Literal['system', 'hardware', 'task', 'targets', 'vision_frame', 'readiness', 'diagnostics', 'calibration']

PROJECTION_EVENT_BY_TOPIC: dict[ProjectionTopic, str] = {
    'system': 'system.state.updated',
    'hardware': 'hardware.state.updated',
    'task': 'task.progress.updated',
    'targets': 'vision.targets.updated',
    'vision_frame': 'vision.frame.updated',
    'readiness': 'readiness.state.updated',
    'diagnostics': 'diagnostics.summary.updated',
    'calibration': 'calibration.profile.updated',
}

EVENT_TOPIC_BY_EVENT: dict[str, ProjectionTopic] = {event: topic for topic, event in PROJECTION_EVENT_BY_TOPIC.items()}

PROJECTION_ORDER: tuple[ProjectionTopic, ...] = (
    'system',
    'readiness',
    'targets',
    'vision_frame',
    'task',
    'hardware',
    'diagnostics',
    'calibration',
)


@dataclass(frozen=True)
class ProjectionEvent:
    """Serializable runtime-projection event.

    Attributes:
        topic: Canonical runtime topic represented by the event.
        event: Public websocket event name.
        data: Projected payload for the topic.
    """

    topic: ProjectionTopic
    event: str
    data: Any


class RuntimeProjectionService:
    """Build public runtime snapshots from the gateway state container."""

    def __init__(self, state: GatewayState) -> None:
        self._state = state

    def project(self, topic: ProjectionTopic) -> Any:
        """Return a projected payload for a runtime topic.

        Args:
            topic: Named runtime projection topic.

        Returns:
            Snapshot payload corresponding to ``topic``.

        Raises:
            KeyError: If ``topic`` is not a supported projection.
        """
        if topic == 'system':
            return self._state.get_system()
        if topic == 'hardware':
            return self._state.get_hardware()
        if topic == 'task':
            return self._state.get_current_task()
        if topic == 'targets':
            return self._state.get_targets()
        if topic == 'vision_frame':
            return self._state.get_vision_frame()
        if topic == 'readiness':
            return self._state.get_readiness()
        if topic == 'diagnostics':
            return self._state.get_diagnostics()
        if topic == 'calibration':
            return self._state.get_calibration()
        raise KeyError(f'unsupported projection topic: {topic}')

    def build_events(self, *topics: ProjectionTopic) -> list[ProjectionEvent]:
        """Build ordered, de-duplicated projection events."""
        requested = {topic for topic in topics}
        events: list[ProjectionEvent] = []
        for topic in PROJECTION_ORDER:
            if topic not in requested:
                continue
            events.append(ProjectionEvent(topic, PROJECTION_EVENT_BY_TOPIC[topic], self.project(topic)))
        return events

    def initial_snapshot_events(self) -> list[ProjectionEvent]:
        """Return the canonical websocket bootstrap snapshot."""
        return self.build_events('system', 'readiness', 'targets', 'vision_frame', 'task', 'hardware', 'diagnostics')
