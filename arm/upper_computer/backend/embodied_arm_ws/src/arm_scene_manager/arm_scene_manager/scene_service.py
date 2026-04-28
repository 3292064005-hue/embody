from __future__ import annotations

import time
from typing import Any

from .attach_manager import AttachManager
from .static_scene import StaticSceneBuilder
from .target_collision_object import TargetCollisionObjectBuilder


class SceneService:
    """Pure runtime scene service shared by the planner and ROS node adapters.

    The service owns deterministic scene-state composition without creating ROS
    publishers/subscriptions. This keeps the scene-building algorithm reusable in
    tests and in non-ROS callers while leaving I/O concerns to
    :class:`SceneManagerNode`.
    """

    provider_mode = 'embedded_core'
    authoritative = False

    def __init__(self, *, provider_mode: str = 'embedded_core', authoritative: bool = False, source_authority: str | None = None) -> None:
        """Initialize scene helpers and the in-memory scene state.

        Returns:
            None.

        Raises:
            Does not raise.

        Boundary behavior:
            The initial snapshot is immediately available even before any target
            is selected or attachment is recorded.
        """
        self.provider_mode = str(provider_mode or 'embedded_core')
        self.authoritative = bool(authoritative)
        self._source_authority = str(source_authority or self.provider_mode or 'embedded_core')
        self.static_scene = StaticSceneBuilder()
        self.target_builder = TargetCollisionObjectBuilder()
        self.attachments = AttachManager()
        self._last_target: dict[str, Any] | None = None
        self._snapshot_counter = 0
        self._last_snapshot = self.build_scene_snapshot()

    def update_target(self, target: dict[str, Any] | None) -> dict[str, Any]:
        """Update the tracked target and rebuild the scene snapshot.

        Args:
            target: Selected target dictionary or ``None`` to clear it.

        Returns:
            dict[str, Any]: Updated scene snapshot.

        Raises:
            ValueError: If ``target`` is present but invalid.
        """
        if target is None:
            self._last_target = None
        else:
            self._last_target = self.target_builder.build(target)
        self._last_snapshot = self.build_scene_snapshot()
        return dict(self._last_snapshot)

    def attach_target(self, target_id: str, *, link_name: str = 'tool0', metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        """Attach one target to the scene and rebuild the snapshot.

        Args:
            target_id: Stable target identifier.
            link_name: Robot link receiving the attachment.
            metadata: Optional attachment metadata.

        Returns:
            dict[str, Any]: Serializable attachment result.

        Raises:
            ValueError: If ``target_id`` or ``link_name`` are empty.
        """
        result = self.attachments.attach(target_id, link_name=link_name, metadata=metadata)
        self._last_snapshot = self.build_scene_snapshot()
        return result

    def detach_target(self, target_id: str) -> dict[str, Any]:
        """Detach one target from the scene and rebuild the snapshot.

        Args:
            target_id: Stable target identifier.

        Returns:
            dict[str, Any]: Serializable detachment result.

        Raises:
            ValueError: If ``target_id`` is empty.
        """
        result = self.attachments.detach(target_id)
        self._last_snapshot = self.build_scene_snapshot()
        return result

    def sync_scene(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Apply a scene-sync payload and return the updated snapshot.

        Args:
            payload: Scene update payload. Supported keys are ``target``,
                ``attach``, and ``detach``.

        Returns:
            dict[str, Any]: Updated scene snapshot.

        Raises:
            ValueError: If ``payload`` is not a dictionary.

        Boundary behavior:
            Missing optional keys are ignored. Invalid attachment/detachment data
            raises immediately so callers do not mistake partial updates for a
            successful scene sync.
        """
        if not isinstance(payload, dict):
            raise ValueError('payload must be a dictionary')
        if 'target' in payload:
            target = payload.get('target')
            self._last_target = None if target is None else self.target_builder.build(dict(target))
        attach = payload.get('attach')
        if isinstance(attach, dict) and attach:
            self.attachments.attach(
                str(attach.get('targetId') or attach.get('target_id') or ''),
                link_name=str(attach.get('linkName', attach.get('link_name', 'tool0'))),
                metadata=dict(attach.get('metadata') or {}),
            )
        detach = payload.get('detach')
        if str(detach or '').strip():
            self.attachments.detach(str(detach).strip())
        self._last_snapshot = self.build_scene_snapshot()
        return dict(self._last_snapshot)

    def build_scene_snapshot(self, target: dict[str, Any] | None = None) -> dict[str, Any]:
        """Return a transport-safe scene snapshot.

        Args:
            target: Optional target override used for one-off snapshot building.

        Returns:
            dict[str, Any]: Scene snapshot with provider metadata and stable IDs.

        Raises:
            ValueError: If the override target is invalid.
        """
        target_object = None
        if target is not None:
            target_object = self.target_builder.build(target)
        elif self._last_target is not None:
            target_object = dict(self._last_target)
        static_scene = self.static_scene.build()
        self._snapshot_counter += 1
        snapshot_id = f'scene-{self._snapshot_counter:06d}'
        snapshot = {
            'sceneAvailable': True,
            'source': 'scene_service',
            'sourceAuthority': self._source_authority,
            'providerMode': self.provider_mode,
            'providerAuthoritative': self.authoritative,
            'snapshotId': snapshot_id,
            'frame': static_scene.get('frame', 'world'),
            'staticScene': static_scene,
            'targetCollisionObject': target_object,
            'attachments': self.attachments.snapshot(),
            'objectCount': len(static_scene.get('objects', [])) + (1 if target_object else 0),
            'updatedAt': round(time.time(), 3),
        }
        return snapshot

    def current_scene(self) -> dict[str, Any]:
        """Return the most recent scene snapshot.

        Returns:
            dict[str, Any]: Last computed snapshot.

        Raises:
            Does not raise.
        """
        return dict(self._last_snapshot)
