from __future__ import annotations

from typing import Any, Callable

try:  # pragma: no cover - depends on ROS runtime availability
    import rclpy
except Exception:  # pragma: no cover
    rclpy = None

try:  # pragma: no cover - optional in non-ROS test environments
    from rclpy.node import Node as _PlainNode  # type: ignore
except Exception:  # pragma: no cover
    _PlainNode = object

try:  # pragma: no cover - depends on ROS runtime availability
    from rclpy.executors import MultiThreadedExecutor  # type: ignore
except Exception:  # pragma: no cover
    MultiThreadedExecutor = None

try:  # pragma: no cover - depends on ROS runtime availability
    from rclpy.lifecycle import LifecycleNode as _LifecycleNode  # type: ignore
    from rclpy.lifecycle import LifecycleState, TransitionCallbackReturn  # type: ignore
    _LIFECYCLE_AVAILABLE = True
except Exception:  # pragma: no cover
    LifecycleState = object
    _LIFECYCLE_AVAILABLE = False

    class TransitionCallbackReturn:
        SUCCESS = 'success'
        FAILURE = 'failure'
        ERROR = 'error'

    class _LifecycleNode(_PlainNode):
        pass


def ros_node_available(node_cls: Any | None) -> bool:
    """Return whether a concrete ROS node class is available.

    Args:
        node_cls: Candidate ROS node class, typically imported from ``rclpy.node``.

    Returns:
        bool: ``True`` when the class is usable and not a non-ROS fallback ``object``.

    Raises:
        Does not raise.

    Boundary behavior:
        ``None`` and placeholder ``object`` values are treated as unavailable.
    """
    return node_cls not in (None, object)



def ros_message_available(message_cls: Any | None) -> bool:
    """Return whether a concrete ROS message class is available.

    Args:
        message_cls: Candidate ROS message class.

    Returns:
        bool: ``True`` when the class is usable and not a fallback ``object``.

    Raises:
        Does not raise.
    """
    return message_cls not in (None, object)



def ros_io_enabled(*, enable_ros_io: bool, node_cls: Any | None = _PlainNode, message_cls: Any | None = None) -> bool:
    """Decide whether a runtime node should create ROS I/O bindings.

    Args:
        enable_ros_io: Caller preference for enabling ROS I/O.
        node_cls: Imported ROS node class.
        message_cls: Optional ROS message class used by the node.

    Returns:
        bool: ``True`` when ROS I/O should be created.

    Raises:
        Does not raise.

    Boundary behavior:
        If ``enable_ros_io`` is false, or required ROS imports are missing,
        the function returns ``False`` so pure-Python tests can instantiate the node.
    """
    if not bool(enable_ros_io):
        return False
    if not ros_node_available(node_cls):
        return False
    if message_cls is not None and not ros_message_available(message_cls):
        return False
    return True


class ManagedLifecycleNode(_LifecycleNode):
    """Compatibility wrapper that exposes ROS managed-lifecycle hooks."""

    def __init__(self, node_name: str, *args: Any, **kwargs: Any) -> None:
        super().__init__(node_name, *args, **kwargs)
        self._runtime_active = not _LIFECYCLE_AVAILABLE
        self._runtime_configured = not _LIFECYCLE_AVAILABLE
        self._managed_publishers: list[Any] = []

    @property
    def runtime_active(self) -> bool:
        return bool(self._runtime_active)

    @property
    def runtime_configured(self) -> bool:
        return bool(self._runtime_configured)

    def create_managed_publisher(self, msg_type: Any, topic: str, qos: Any) -> Any:
        if _LIFECYCLE_AVAILABLE and hasattr(self, 'create_lifecycle_publisher'):
            publisher = self.create_lifecycle_publisher(msg_type, topic, qos)  # type: ignore[attr-defined]
            self._managed_publishers.append(publisher)
            return publisher
        return self.create_publisher(msg_type, topic, qos)  # type: ignore[attr-defined]

    def on_configure(self, state: LifecycleState) -> Any:  # pragma: no cover
        del state
        self._runtime_configured = True
        return TransitionCallbackReturn.SUCCESS

    def on_activate(self, state: LifecycleState) -> Any:  # pragma: no cover
        del state
        for publisher in self._managed_publishers:
            try:
                publisher.on_activate()
            except Exception:
                continue
        self._runtime_active = True
        return TransitionCallbackReturn.SUCCESS

    def on_deactivate(self, state: LifecycleState) -> Any:  # pragma: no cover
        del state
        self._runtime_active = False
        for publisher in self._managed_publishers:
            try:
                publisher.on_deactivate()
            except Exception:
                continue
        return TransitionCallbackReturn.SUCCESS

    def on_cleanup(self, state: LifecycleState) -> Any:  # pragma: no cover
        del state
        self._runtime_active = False
        self._runtime_configured = False
        return TransitionCallbackReturn.SUCCESS

    def on_shutdown(self, state: LifecycleState) -> Any:  # pragma: no cover
        del state
        self._runtime_active = False
        return TransitionCallbackReturn.SUCCESS

    def on_error(self, state: LifecycleState) -> Any:  # pragma: no cover
        del state
        self._runtime_active = False
        return TransitionCallbackReturn.SUCCESS



def lifecycle_available() -> bool:
    return _LIFECYCLE_AVAILABLE



def lifecycle_main(factory: Callable[[], Any], args: list[str] | None = None) -> None:
    if rclpy is None:  # pragma: no cover
        raise RuntimeError('rclpy unavailable')
    rclpy.init(args=args)
    node = factory()
    executor = MultiThreadedExecutor() if MultiThreadedExecutor is not None else None
    try:
        if executor is None:
            rclpy.spin(node)
        else:
            executor.add_node(node)
            executor.spin()
    finally:
        try:
            node.destroy_node()
        finally:
            if executor is not None:
                try:
                    executor.shutdown()
                except Exception:
                    pass
            rclpy.shutdown()
