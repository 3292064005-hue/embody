from __future__ import annotations

"""Shared runtime-service transport helpers for scene/grasp boundaries.

The repository uses one deterministic fallback path for pure-Python tests and
one ROS-service path for real runtime deployments. Both paths share the same
JSON request/response envelope so planner, scene-manager, and grasp-planner
agree on one runtime-service contract.
"""

import json
from dataclasses import dataclass
from threading import RLock
from typing import Any, Callable

try:  # pragma: no cover - depends on ROS runtime availability
    import rclpy
except Exception:  # pragma: no cover
    rclpy = None


class RuntimeServiceError(RuntimeError):
    """Raised when a runtime service request cannot be completed."""


@dataclass(frozen=True)
class RuntimeServiceResult:
    """Normalized runtime-service response envelope.

    Attributes:
        ok: Whether the service completed successfully.
        payload: JSON-serializable response payload.
        error: Operator/debug message when ``ok`` is false.
    """

    ok: bool
    payload: dict[str, Any]
    error: str = ''


class LocalRuntimeServiceRegistry:
    """Process-local fallback registry used when ROS services are unavailable.

    Boundary behavior:
        - Registering a service name replaces any previous handler.
        - Calling an unknown service raises :class:`RuntimeServiceError`.
        - Exceptions raised by handlers are converted into deterministic
          runtime-service errors so callers do not misinterpret partial work
          as a successful boundary call.
    """

    def __init__(self) -> None:
        self._handlers: dict[str, Callable[[dict[str, Any]], RuntimeServiceResult]] = {}
        self._lock = RLock()

    def register(self, name: str, handler: Callable[[dict[str, Any]], RuntimeServiceResult]) -> None:
        normalized = str(name or '').strip()
        if not normalized:
            raise ValueError('service name must be non-empty')
        with self._lock:
            self._handlers[normalized] = handler

    def unregister(self, name: str, handler: Callable[[dict[str, Any]], RuntimeServiceResult] | None = None) -> None:
        normalized = str(name or '').strip()
        if not normalized:
            return
        with self._lock:
            current = self._handlers.get(normalized)
            if current is None:
                return
            if handler is None or current is handler:
                self._handlers.pop(normalized, None)

    def contains(self, name: str) -> bool:
        normalized = str(name or '').strip()
        if not normalized:
            return False
        with self._lock:
            return normalized in self._handlers

    def call(self, name: str, request: dict[str, Any]) -> RuntimeServiceResult:
        normalized = str(name or '').strip()
        if not normalized:
            raise RuntimeServiceError('service name must be non-empty')
        with self._lock:
            handler = self._handlers.get(normalized)
        if handler is None:
            raise RuntimeServiceError(f'runtime service unavailable: {normalized}')
        try:
            result = handler(dict(request or {}))
        except RuntimeServiceError:
            raise
        except Exception as exc:
            raise RuntimeServiceError(f'runtime service failed: {normalized}: {exc}') from exc
        if not isinstance(result, RuntimeServiceResult):
            raise RuntimeServiceError(f'runtime service returned invalid result type: {normalized}')
        if not result.ok:
            raise RuntimeServiceError(result.error or f'runtime service rejected request: {normalized}')
        return result


LOCAL_RUNTIME_SERVICE_REGISTRY = LocalRuntimeServiceRegistry()


def encode_runtime_service_payload(payload: dict[str, Any]) -> str:
    """Serialize one runtime-service payload to canonical JSON."""
    if not isinstance(payload, dict):
        raise ValueError('payload must be a dictionary')
    return json.dumps(payload, ensure_ascii=False, separators=(',', ':'))


def decode_runtime_service_payload(payload: str, *, field_name: str) -> dict[str, Any]:
    """Deserialize one runtime-service payload from canonical JSON."""
    text = str(payload or '').strip()
    if not text:
        return {}
    try:
        parsed = json.loads(text)
    except Exception as exc:
        raise RuntimeServiceError(f'invalid {field_name}: {exc}') from exc
    if not isinstance(parsed, dict):
        raise RuntimeServiceError(f'{field_name} must decode to a dictionary')
    return parsed


def build_runtime_service_response(*, payload: dict[str, Any] | None = None, error: str = '') -> RuntimeServiceResult:
    """Build a normalized runtime-service response envelope."""
    normalized_error = str(error or '').strip()
    return RuntimeServiceResult(ok=not normalized_error, payload=dict(payload or {}), error=normalized_error)


class LocalRuntimeServiceClient:
    """Fallback runtime-service client backed by the local registry."""

    def __init__(self, service_name: str) -> None:
        self.service_name = str(service_name or '').strip()
        if not self.service_name:
            raise ValueError('service_name must be non-empty')

    def is_available(self) -> bool:
        """Return whether the process-local boundary is currently registered."""
        return LOCAL_RUNTIME_SERVICE_REGISTRY.contains(self.service_name)

    def boundary_status(self) -> tuple[bool, str]:
        """Return one local-boundary health tuple."""
        if self.is_available():
            return True, 'local_runtime_service_ready'
        return False, 'local_runtime_service_unavailable'

    def call(self, request: dict[str, Any]) -> dict[str, Any]:
        result = LOCAL_RUNTIME_SERVICE_REGISTRY.call(self.service_name, request)
        return dict(result.payload)


class RosJsonRuntimeServiceClient:
    """ROS runtime-service client using the shared JSON envelope.

    Boundary behavior:
        - Pure-Python tests may opt into a process-local fallback.
        - Live runtime lanes can disable the fallback so missing ROS service
          declarations surface as hard readiness failures.
        - Service-unavailable, timeout, and malformed-response cases raise
          :class:`RuntimeServiceError` so planner callers fail closed.
    """

    def __init__(
        self,
        *,
        node: Any,
        service_name: str,
        srv_type: Any,
        response_json_field: str,
        timeout_sec: float = 1.0,
        fallback_client: LocalRuntimeServiceClient | None = None,
        allow_local_fallback: bool = True,
    ) -> None:
        self._node = node
        self._service_name = str(service_name or '').strip()
        self._srv_type = srv_type
        self._response_json_field = str(response_json_field or '').strip()
        self._timeout_sec = float(timeout_sec)
        self._fallback = fallback_client or LocalRuntimeServiceClient(self._service_name)
        self._allow_local_fallback = bool(allow_local_fallback)
        if not self._service_name:
            raise ValueError('service_name must be non-empty')
        if not self._response_json_field:
            raise ValueError('response_json_field must be non-empty')
        self._client = None
        if rclpy is not None and srv_type is not object and hasattr(node, 'create_client'):
            try:
                self._client = node.create_client(srv_type, self._service_name)
            except Exception:
                self._client = None

    def _fallback_available(self) -> bool:
        return self._allow_local_fallback and self._fallback.is_available()

    def boundary_status(self) -> tuple[bool, str]:
        """Return `(ready, detail)` for this runtime-service boundary.

        The method distinguishes three cases:
        - ROS boundary is ready.
        - ROS boundary is expected but missing / unavailable.
        - Local fallback is intentionally enabled for pure-Python test paths.
        """
        if self._client is not None and rclpy is not None and self._srv_type is not object:
            try:
                if self._client.wait_for_service(timeout_sec=0.0):
                    return True, 'ros_runtime_service_ready'
                return False, 'ros_runtime_service_unavailable'
            except Exception as exc:
                return False, f'ros_runtime_service_probe_failed: {exc}'
        if self._srv_type is object:
            if self._fallback_available():
                return True, 'local_runtime_service_ready'
            return False, 'runtime_service_interface_unavailable'
        if rclpy is None:
            if self._fallback_available():
                return True, 'local_runtime_service_ready'
            return False, 'ros_runtime_unavailable'
        if self._fallback_available():
            return True, 'local_runtime_service_ready'
        return False, 'ros_runtime_service_client_unavailable'

    def call(self, request: dict[str, Any]) -> dict[str, Any]:
        ready, detail = self.boundary_status()
        if self._client is None or rclpy is None or self._srv_type is object:
            if self._fallback_available():
                return self._fallback.call(request)
            raise RuntimeServiceError(f'runtime service unavailable: {self._service_name}: {detail}')
        if not ready:
            raise RuntimeServiceError(f'runtime service unavailable: {self._service_name}: {detail}')
        req = self._srv_type.Request()
        req.request_json = encode_runtime_service_payload(request)
        future = self._client.call_async(req)
        try:
            rclpy.spin_until_future_complete(self._node, future, timeout_sec=self._timeout_sec)
        except Exception as exc:
            raise RuntimeServiceError(f'runtime service failed: {self._service_name}: {exc}') from exc
        if not future.done():
            raise RuntimeServiceError(f'runtime service timeout: {self._service_name}')
        response = future.result()
        if response is None:
            raise RuntimeServiceError(f'runtime service returned no response: {self._service_name}')
        if not bool(getattr(response, 'ok', False)):
            raise RuntimeServiceError(str(getattr(response, 'error', '') or f'runtime service rejected request: {self._service_name}'))
        return decode_runtime_service_payload(getattr(response, self._response_json_field, ''), field_name=self._response_json_field)
