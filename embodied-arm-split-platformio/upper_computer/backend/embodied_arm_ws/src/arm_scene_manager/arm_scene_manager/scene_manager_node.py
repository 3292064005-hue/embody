from __future__ import annotations

import json
import time
from typing import Any

try:
    import rclpy
    from arm_backend_common.lifecycle_support import ManagedLifecycleNode, lifecycle_main, ros_io_enabled
    from std_msgs.msg import String
    from arm_common import TopicNames
except Exception:  # pragma: no cover
    rclpy = None
    ManagedLifecycleNode = object

    def lifecycle_main(factory, args=None):
        del factory, args
        raise RuntimeError('rclpy unavailable')

    def ros_io_enabled(*, enable_ros_io: bool, message_cls=None):
        del message_cls
        return False

    String = object

    class TopicNames:
        INTERNAL_SELECTED_TARGET = '/arm/internal/selected_target'
        INTERNAL_SYNC_SCENE = '/arm/internal/sync_scene'
        SCENE_SUMMARY = '/arm/scene/summary'

from .attach_manager import AttachManager
from .static_scene import StaticSceneBuilder
from .target_collision_object import TargetCollisionObjectBuilder


class SceneManagerNode(ManagedLifecycleNode):
    """Runtime scene manager that maintains a serializable planning scene.

    The node can operate both as a plain Python object for unit tests and as a
    ROS node when ``rclpy`` is available. It normalizes the static workspace,
    the currently selected target collision object, and the active attachment
    set into a single runtime scene snapshot.
    """

    def __init__(self, *, enable_ros_io: bool = True) -> None:
        """Initialize scene builders, state, and ROS I/O when available.

        Args:
            enable_ros_io: Whether ROS publishers/subscriptions should be created.

        Returns:
            None.

        Raises:
            Does not raise directly.
        """
        self._ros_enabled = ros_io_enabled(enable_ros_io=enable_ros_io, message_cls=String)
        if self._ros_enabled:
            super().__init__('scene_manager')
        self.static_scene = StaticSceneBuilder()
        self.target_builder = TargetCollisionObjectBuilder()
        self.attachments = AttachManager()
        self._last_target: dict[str, Any] | None = None
        self._last_snapshot = self.build_scene_snapshot()
        self._summary_pub = self.create_managed_publisher(String, TopicNames.SCENE_SUMMARY, 10) if self._ros_enabled else None
        if self._ros_enabled:
            self.create_subscription(String, TopicNames.INTERNAL_SELECTED_TARGET, self._on_selected_target, 20)
            self.create_subscription(String, TopicNames.INTERNAL_SYNC_SCENE, self._on_sync_scene, 20)

    def update_target(self, target: dict[str, Any] | None) -> dict[str, Any]:
        """Update the current runtime target and rebuild the scene snapshot.

        Args:
            target: Selected target dictionary or ``None``.

        Returns:
            dict[str, Any]: Updated scene snapshot.

        Raises:
            ValueError: If ``target`` is not ``None`` and cannot be normalized.
        """
        if target is None:
            self._last_target = None
        else:
            self._last_target = self.target_builder.build(target)
        self._last_snapshot = self.build_scene_snapshot()
        self._publish_snapshot()
        return dict(self._last_snapshot)

    def attach_target(self, target_id: str, *, link_name: str = 'tool0', metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        """Attach a target to the runtime scene and publish the updated snapshot."""
        result = self.attachments.attach(target_id, link_name=link_name, metadata=metadata)
        self._last_snapshot = self.build_scene_snapshot()
        self._publish_snapshot()
        return result

    def detach_target(self, target_id: str) -> dict[str, Any]:
        """Detach a target from the runtime scene and publish the updated snapshot."""
        result = self.attachments.detach(target_id)
        self._last_snapshot = self.build_scene_snapshot()
        self._publish_snapshot()
        return result

    def sync_scene(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Apply a scene-sync payload and return the updated snapshot.

        Args:
            payload: Scene synchronization payload that may include ``target``,
                ``attach`` or ``detach`` entries.

        Returns:
            dict[str, Any]: Updated scene snapshot.

        Raises:
            ValueError: If ``payload`` is not a dictionary.
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
        self._publish_snapshot()
        return dict(self._last_snapshot)

    def build_scene_snapshot(self, target: dict[str, Any] | None = None) -> dict[str, Any]:
        """Return the current runtime scene snapshot.

        Args:
            target: Optional target dictionary overriding the tracked target.

        Returns:
            dict[str, Any]: Runtime planning-scene snapshot.

        Raises:
            ValueError: If the override target is invalid.
        """
        target_object = None
        if target is not None:
            target_object = self.target_builder.build(target)
        elif self._last_target is not None:
            target_object = dict(self._last_target)
        static_scene = self.static_scene.build()
        snapshot = {
            'sceneAvailable': True,
            'source': 'scene_manager',
            'frame': static_scene.get('frame', 'world'),
            'staticScene': static_scene,
            'targetCollisionObject': target_object,
            'attachments': self.attachments.snapshot(),
            'objectCount': len(static_scene.get('objects', [])) + (1 if target_object else 0),
            'updatedAt': round(time.time(), 3),
        }
        return snapshot

    def current_scene(self) -> dict[str, Any]:
        """Return the last published scene snapshot."""
        return dict(self._last_snapshot)

    def _publish_snapshot(self) -> None:
        if self._ros_enabled and not self.runtime_active:
            return
        """Publish the current scene snapshot when ROS publishers are available."""
        if self._summary_pub is None or String is object:
            return
        self._summary_pub.publish(String(data=json.dumps(self._last_snapshot, ensure_ascii=False)))

    def _on_selected_target(self, msg: String) -> None:
        if self._ros_enabled and not self.runtime_active:
            return
        """Update the current scene target from a ROS topic payload."""
        payload = self._parse_json(msg.data)
        target = payload.get('target') if 'target' in payload else payload
        self.update_target(target or None)

    def _on_sync_scene(self, msg: String) -> None:
        if self._ros_enabled and not self.runtime_active:
            return
        """Apply a serialized scene-sync payload from ROS."""
        payload = self._parse_json(msg.data)
        if payload:
            self.sync_scene(payload)

    @staticmethod
    def _parse_json(payload: str) -> dict[str, Any]:
        """Parse a JSON payload into a dictionary."""
        if not payload:
            return {}
        try:
            parsed = json.loads(payload)
        except Exception:
            return {}
        return parsed if isinstance(parsed, dict) else {}


def main(args=None) -> None:
    """Run the scene manager node when ROS is available."""
    if rclpy is None:
        SceneManagerNode(enable_ros_io=False)
        return
    lifecycle_main(SceneManagerNode, args=args)
