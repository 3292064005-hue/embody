from __future__ import annotations

import sys
from types import SimpleNamespace
from typing import Any, Callable

try:  # pragma: no cover - depends on ROS runtime availability
    import rclpy
except Exception:  # pragma: no cover
    rclpy = None


def _resolve_plain_node_class() -> Any | None:
    """Resolve the current ``rclpy.node.Node`` class without trusting import order.

    Args:
        None.

    Returns:
        Current ROS node class when available, otherwise ``None``.

    Raises:
        Does not raise.

    Boundary behavior:
        When the module graph is partially stubbed during tests, the function
        consults ``sys.modules`` before attempting a fresh import so later test
        injections become visible even if this module was imported earlier.
    """
    module = sys.modules.get('rclpy.node')
    node_cls = getattr(module, 'Node', None) if module is not None else None
    if node_cls is not None:
        return node_cls
    try:  # pragma: no cover - depends on ROS runtime availability
        from rclpy.node import Node as node_cls  # type: ignore
        return node_cls
    except Exception:  # pragma: no cover
        return None


_PlainNode = _resolve_plain_node_class() or object

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


class _ParameterValueProxy:
    """Minimal parameter-value proxy for non-ROS fallback nodes."""

    def __init__(self, value: Any) -> None:
        self.string_value = value if isinstance(value, str) else ''
        self.integer_value = int(value) if isinstance(value, bool | int) else 0
        self.double_value = float(value) if isinstance(value, bool | int | float) else 0.0
        self.bool_value = bool(value)


class _ParameterProxy:
    """Minimal parameter proxy matching the ROS API used by tests."""

    def __init__(self, value: Any) -> None:
        self.value = value

    def get_parameter_value(self) -> _ParameterValueProxy:
        return _ParameterValueProxy(self.value)


class _FallbackLogger:
    """No-op logger used when ROS node APIs are unavailable."""

    def info(self, *_args: Any, **_kwargs: Any) -> None:
        return None

    def warn(self, *_args: Any, **_kwargs: Any) -> None:
        return None

    def error(self, *_args: Any, **_kwargs: Any) -> None:
        return None


class _FallbackPublisher:
    """Collect-only publisher used in pure-Python fallback paths."""

    def __init__(self) -> None:
        self.messages: list[Any] = []

    def publish(self, message: Any) -> None:
        self.messages.append(message)


class _FallbackNodeProxy:
    """Minimal ROS-node shim for import-order-independent non-ROS tests.

    The shim intentionally implements only the node surface used across the
    repository's pure-Python tests. Runtime code should still execute on real
    ROS nodes; this shim exists solely to keep test instantiation deterministic
    when ``lifecycle_support`` was imported before the test injected ROS stubs.
    """

    def __init__(self, node_name: str, *_args: Any, **_kwargs: Any) -> None:
        self.node_name = str(node_name)
        self._parameters: dict[str, Any] = {}
        self.publishers: list[Any] = []
        self.subscriptions: list[tuple[Any, str, Any]] = []
        self.services: list[tuple[Any, str, Any]] = []
        self.timers: list[tuple[Any, Any]] = []
        self._logger = _FallbackLogger()

    def declare_parameter(self, name: str, value: Any) -> None:
        self._parameters[str(name)] = value

    def get_parameter(self, name: str) -> _ParameterProxy:
        return _ParameterProxy(self._parameters.get(str(name), ''))

    def create_publisher(self, *_args: Any, **_kwargs: Any) -> _FallbackPublisher:
        publisher = _FallbackPublisher()
        self.publishers.append(publisher)
        return publisher

    def create_subscription(self, msg_type: Any, topic: str, callback: Any, *_args: Any, **_kwargs: Any) -> Any:
        handle = SimpleNamespace(msg_type=msg_type, topic=str(topic), callback=callback)
        self.subscriptions.append((msg_type, str(topic), callback))
        return handle

    def create_service(self, srv_type: Any, name: str, callback: Any, *_args: Any, **_kwargs: Any) -> Any:
        handle = SimpleNamespace(srv_type=srv_type, name=str(name), callback=callback)
        self.services.append((srv_type, str(name), callback))
        return handle

    def create_timer(self, period: Any, callback: Any, *_args: Any, **_kwargs: Any) -> Any:
        handle = SimpleNamespace(period=period, callback=callback)
        self.timers.append((period, callback))
        return handle

    def get_logger(self) -> _FallbackLogger:
        return self._logger

    def destroy_node(self) -> None:
        return None


def ros_node_available(node_cls: Any | None) -> bool:
    """Return whether a concrete ROS node class is available.

    Args:
        node_cls: Candidate ROS node class, typically imported from ``rclpy.node``.

    Returns:
        bool: ``True`` when the class is usable and not a non-ROS fallback ``object``.

    Raises:
        Does not raise.

    Boundary behavior:
        ``None`` and sentinel ``object`` values are treated as unavailable.
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
    """Compatibility wrapper that exposes ROS managed-lifecycle hooks.

    The wrapper remains a real lifecycle node in ROS environments. When tests
    import this module before they inject ``rclpy`` stubs, the class falls back
    to a delegated plain-node proxy instead of permanently freezing to
    ``object.__init__`` semantics.
    """

    def __init__(self, node_name: str, *args: Any, **kwargs: Any) -> None:
        self._fallback_node: Any | None = None
        if _LIFECYCLE_AVAILABLE:
            super().__init__(node_name, *args, **kwargs)
        else:
            node_cls = _resolve_plain_node_class()
            if ros_node_available(node_cls) and isinstance(self, node_cls):
                node_cls.__init__(self, node_name, *args, **kwargs)
            elif ros_node_available(node_cls):
                self._fallback_node = node_cls(node_name, *args, **kwargs)
            else:
                self._fallback_node = _FallbackNodeProxy(node_name, *args, **kwargs)
        self._runtime_active = not _LIFECYCLE_AVAILABLE
        self._runtime_configured = not _LIFECYCLE_AVAILABLE
        self._managed_publishers: list[Any] = []

    def __getattr__(self, name: str) -> Any:
        fallback_node = self.__dict__.get('_fallback_node')
        if fallback_node is not None:
            return getattr(fallback_node, name)
        raise AttributeError(name)

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
